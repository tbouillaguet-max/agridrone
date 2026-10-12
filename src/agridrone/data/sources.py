"""Registre des sources de données, téléchargement idempotent et vérification d'intégrité.

* Le registre (``configs/data/sources.yaml``) décrit chaque source : licence, preuve de
  vérification, attribution, fichiers et sommes de contrôle publiées.
* :func:`download_file` télécharge en flux vers un fichier ``.part``, calcule md5 et
  sha256 au passage, vérifie taille et empreintes, puis renomme de façon atomique. Un
  fichier déjà présent et conforme n'est pas retéléchargé.
* Quand le fournisseur ne publie pas d'empreinte (Kaggle, GFZ), le premier
  téléchargement l'enregistre dans ``sources.lock.yaml`` (versionné) ; les suivants
  sont vérifiés contre elle.
* :func:`extract_archive` extrait ZIP et RAR en refusant les chemins absolus, les
  remontées ``..`` et les liens symboliques.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import zipfile
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath
from typing import Any, Literal

import requests
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from agridrone.core.config import ConfigError, dump_yaml, load_yaml

#: Licences jugées compatibles avec un usage commercial (identifiants SPDX).
COMMERCIAL_LICENSES = frozenset(
    {"CC-BY-4.0", "CC0-1.0", "CDLA-Permissive-1.0", "MIT", "Apache-2.0"}
)

_CHUNK = 1 << 20
_TIMEOUT = (30, 300)  # (connexion, lecture) en secondes


class IntegrityError(RuntimeError):
    """Taille ou empreinte d'un fichier différente de celle attendue."""


class UnsafeArchiveError(RuntimeError):
    """Archive contenant un chemin dangereux (absolu, ``..``, lien symbolique)."""


# ---------------------------------------------------------------------------
# Registre
# ---------------------------------------------------------------------------


class SourceFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    url: str
    size: int | None = None
    md5: str | None = None
    sha256: str | None = None
    #: Motifs (fnmatch) des membres à extraire d'une archive ZIP ; par défaut, tout.
    #: Sert à ne garder qu'une partie d'une grosse archive (ex. les images originales
    #: sans les images augmentées, qui ne doivent jamais servir de test).
    extract_only: list[str] | None = None

    @field_validator("name")
    @classmethod
    def _plain_file_name(cls, value: str) -> str:
        if not value or "/" in value or "\\" in value or value in {".", ".."}:
            raise ValueError(f"nom de fichier invalide : {value!r}")
        return value


#: Projet servi par une source : ``wheat`` (blé, y compris les jeux qui valident la chaîne
#: multispectrale du blé, comme WeedsGalore) ou ``olive`` (olivier).
Project = Literal["wheat", "olive"]


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    project: Project
    task: Literal["classification", "detection", "segmentation"]
    status: Literal["retained", "candidate", "excluded"]
    license: str
    license_evidence: str
    attribution: str
    provider: Literal["zenodo", "mendeley", "kaggle", "gfz", "url"]
    homepage: str
    notes: str = ""
    files: list[SourceFile] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_status(self) -> Source:
        if self.status == "retained" and self.license not in COMMERCIAL_LICENSES:
            raise ValueError(
                f"licence {self.license!r} incompatible avec le statut 'retained' "
                f"(autorisées : {', '.join(sorted(COMMERCIAL_LICENSES))})"
            )
        if self.status != "excluded" and not self.files:
            raise ValueError("une source téléchargeable doit lister ses fichiers")
        return self


class Registry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sources: dict[str, Source]

    def selected(
        self, ids: list[str] | None, include_candidates: bool, project: Project | None = None
    ) -> dict[str, Source]:
        """Sources à traiter : ``ids`` explicites, sinon toutes les ``retained``
        (plus les ``candidate`` si demandé), éventuellement limitées à un ``project``.
        Une source exclue n'est jamais renvoyée."""
        if ids:
            unknown = [i for i in ids if i not in self.sources]
            if unknown:
                raise ConfigError(f"Sources inconnues : {', '.join(unknown)}")
            chosen = {i: self.sources[i] for i in ids}
            excluded = [i for i, s in chosen.items() if s.status == "excluded"]
            if excluded:
                raise ConfigError(f"Sources exclues, non téléchargeables : {', '.join(excluded)}")
            return chosen
        allowed = {"retained", "candidate"} if include_candidates else {"retained"}
        return {
            i: s
            for i, s in self.sources.items()
            if s.status in allowed and (project is None or s.project == project)
        }


def load_registry(path: str | Path) -> Registry:
    try:
        return Registry.model_validate(load_yaml(path))
    except ValidationError as exc:
        raise ConfigError(f"{path} : registre de sources invalide\n{exc}") from exc


class LockFile:
    """Empreintes enregistrées au premier téléchargement (fichiers sans somme publiée)."""

    HEADER = "Généré par `agridrone data download` : ne pas modifier à la main."

    def __init__(self, path: Path) -> None:
        self.path = path
        data = load_yaml(path) if path.exists() else {}
        self.entries: dict[str, dict[str, Any]] = dict(data.get("files") or {})

    def get(self, key: str) -> dict[str, Any] | None:
        return self.entries.get(key)

    def record(self, key: str, sha256: str, size: int) -> None:
        self.entries[key] = {"sha256": sha256, "size": size}
        self._save()

    def prune(self, registry: Registry) -> None:
        """Retire les entrées des fichiers qui ne figurent plus dans le registre."""
        valid = {f"{sid}/{f.name}" for sid, src in registry.sources.items() for f in src.files}
        stale = set(self.entries) - valid
        if stale:
            for key in stale:
                del self.entries[key]
            self._save()

    def _save(self) -> None:
        dump_yaml({"comment": self.HEADER, "files": dict(sorted(self.entries.items()))}, self.path)


# ---------------------------------------------------------------------------
# Téléchargement et vérification
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Digests:
    md5: str
    sha256: str
    size: int


@dataclass(frozen=True)
class DownloadResult:
    path: Path
    status: Literal["downloaded", "present"]
    digests: Digests


def _hash_chunks(chunks: Iterator[bytes], sink: Any | None = None) -> Digests:
    md5, sha256, size = hashlib.md5(usedforsecurity=False), hashlib.sha256(), 0
    for chunk in chunks:
        md5.update(chunk)
        sha256.update(chunk)
        size += len(chunk)
        if sink is not None:
            sink.write(chunk)
    return Digests(md5.hexdigest(), sha256.hexdigest(), size)


def file_digests(path: Path) -> Digests:
    with path.open("rb") as fh:
        return _hash_chunks(iter(lambda: fh.read(_CHUNK), b""))


def check_digests(digests: Digests, file: SourceFile, locked: dict[str, Any] | None) -> None:
    """Lève :class:`IntegrityError` si la taille ou une empreinte attendue diffère."""
    expected = {
        "size": file.size if file.size is not None else (locked or {}).get("size"),
        "md5": file.md5,
        "sha256": file.sha256 or (locked or {}).get("sha256"),
    }
    actual = {"size": digests.size, "md5": digests.md5, "sha256": digests.sha256}
    errors = [
        f"{key} attendu {value}, obtenu {actual[key]}"
        for key, value in expected.items()
        if value is not None and value != actual[key]
    ]
    if errors:
        raise IntegrityError(f"{file.name} : " + " ; ".join(errors))


def _with_progress(chunks: Iterator[bytes], total: int | None, desc: str) -> Iterator[bytes]:
    from tqdm import tqdm

    with tqdm(total=total, unit="B", unit_scale=True, desc=desc, leave=False) as bar:
        for chunk in chunks:
            bar.update(len(chunk))
            yield chunk


def _session_for(provider: str) -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = "agridrone-data/0.1"
    if provider == "kaggle":
        user, key = os.environ.get("KAGGLE_USERNAME"), os.environ.get("KAGGLE_KEY")
        if user and key:  # facultatif : les jeux publics se téléchargent sans compte
            session.auth = (user, key)
    return session


def download_file(
    source_id: str,
    file: SourceFile,
    raw_dir: Path,
    lock: LockFile,
    session: requests.Session,
    *,
    progress: bool = False,
) -> DownloadResult:
    """Télécharge ``file`` dans ``raw_dir/source_id/`` s'il n'y est pas déjà, conforme."""
    dest = raw_dir / source_id / file.name
    key = f"{source_id}/{file.name}"
    locked = lock.get(key)

    if dest.exists():
        digests = file_digests(dest)
        try:
            check_digests(digests, file, locked)
        except IntegrityError as exc:
            raise IntegrityError(
                f"{dest} est présent mais non conforme ({exc}). "
                "Le supprimer pour forcer un nouveau téléchargement."
            ) from exc
        return DownloadResult(dest, "present", digests)

    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    try:
        with session.get(file.url, stream=True, timeout=_TIMEOUT) as response:
            response.raise_for_status()
            chunks: Iterator[bytes] = response.iter_content(chunk_size=_CHUNK)
            if progress:
                total = int(response.headers.get("Content-Length", 0)) or file.size
                chunks = _with_progress(chunks, total, key)
            with part.open("wb") as sink:
                digests = _hash_chunks(chunks, sink)
        check_digests(digests, file, locked)
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    os.replace(part, dest)

    if file.md5 is None and file.sha256 is None and locked is None:
        lock.record(key, digests.sha256, digests.size)
    return DownloadResult(dest, "downloaded", digests)


def write_manifest(
    source_id: str, source: Source, results: list[DownloadResult], raw_dir: Path
) -> Path:
    """Écrit ``raw_dir/source_id/SOURCE.json`` : licence, attribution, empreintes."""
    manifest = {
        "source_id": source_id,
        "title": source.title,
        "license": source.license,
        "license_evidence": source.license_evidence,
        "attribution": source.attribution,
        "homepage": source.homepage,
        "status": source.status,
        "checked_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "files": [
            {
                "name": r.path.name,
                "sha256": r.digests.sha256,
                "md5": r.digests.md5,
                "size": r.digests.size,
            }
            for r in results
        ],
    }
    path = raw_dir / source_id / "SOURCE.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Extraction sécurisée
# ---------------------------------------------------------------------------


def _check_member(name: str) -> None:
    pure = PurePosixPath(name.replace("\\", "/"))
    if pure.is_absolute() or ".." in pure.parts or (pure.parts and ":" in pure.parts[0]):
        raise UnsafeArchiveError(f"chemin refusé dans l'archive : {name!r}")


def _extract_zip(archive: Path, dest: Path, include: Sequence[str] | None = None) -> None:
    with zipfile.ZipFile(archive) as zf:
        members = zf.infolist()
        for member in members:
            _check_member(member.filename)
            if (member.external_attr >> 16) & 0o170000 == 0o120000:
                raise UnsafeArchiveError(f"lien symbolique refusé : {member.filename!r}")
        if include is not None:
            members = [m for m in members if any(fnmatch(m.filename, pat) for pat in include)]
            if not members:
                raise ValueError(f"{archive.name} : aucun membre ne correspond à {list(include)}")
        _check_free_space(sum(m.file_size for m in members), dest)
        zf.extractall(dest, members=members)


#: Outils d'extraction RAR, par ordre de préférence (exécutable, archive, destination).
#: Le décodeur RAR de libarchive (bsdtar) échoue sur certaines archives (erreurs CRC) :
#: il ne sert qu'en dernier recours.
_RAR_TOOLS: tuple[tuple[str, Callable[[str, Path, Path], list[str]]], ...] = (
    ("unar", lambda exe, a, d: [exe, "-q", "-D", "-o", str(d), str(a)]),
    ("unrar", lambda exe, a, d: [exe, "x", "-o+", "-idq", str(a), f"{d}/"]),
    ("7z", lambda exe, a, d: [exe, "x", "-y", f"-o{d}", str(a)]),
    ("bsdtar", lambda exe, a, d: [exe, "-xf", str(a), "-C", str(d)]),
)


def find_tool(name: str, *, windows: bool = os.name == "nt") -> str | None:
    """Chemin d'un outil d'extraction : le PATH, puis, sous Windows, les emplacements
    usuels (7-Zip ne s'ajoute pas au PATH ; le ``tar.exe`` de Windows 10+ est un bsdtar)."""
    found = shutil.which(name)
    if found or not windows:
        return found
    if name == "7z":
        for base in (os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)")):
            if base and (exe := Path(base) / "7-Zip" / "7z.exe").is_file():
                return str(exe)
    if name == "bsdtar":
        return shutil.which("tar")
    return None


def _extract_rar(archive: Path, dest: Path) -> None:
    for tool, command in _RAR_TOOLS:
        exe = find_tool(tool)
        if exe:
            if tool == "bsdtar":  # seul outil dont on contrôle la liste avant extraction
                listing = subprocess.run(
                    [exe, "-tf", str(archive)], capture_output=True, text=True, check=True
                ).stdout.splitlines()
                for name in listing:
                    _check_member(name)
            subprocess.run(command(exe, archive, dest), check=True)
            break
    else:
        raise RuntimeError(
            f"{archive.name} : aucun outil d'extraction RAR trouvé. Installer 7-Zip "
            "(Windows : https://www.7-zip.org), unar (apt install unar, brew install unar) "
            "ou unrar."
        )
    root = dest.resolve()
    for path in dest.rglob("*"):
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise UnsafeArchiveError(f"chemin refusé après extraction : {path}")


def _check_free_space(needed: int, dest: Path) -> None:
    free = shutil.disk_usage(dest).free
    if needed > 0.95 * free:
        raise OSError(
            f"espace disque insuffisant : {needed / 1e9:.1f} Go requis, {free / 1e9:.1f} Go libres"
        )


def extract_archive(archive: Path, dest: Path, include: Sequence[str] | None = None) -> Path:
    """Extrait ``archive`` dans ``dest`` (idempotent : marqueur ``.extracted``).

    L'extraction se fait dans un dossier temporaire, renommé à la fin : une
    extraction interrompue ne laisse jamais un ``dest`` incomplet. ``include`` limite
    l'extraction aux membres qui correspondent à l'un des motifs (ZIP seulement).
    """
    marker = dest / ".extracted"
    if marker.exists():
        return dest
    tmp = dest.with_name(dest.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    try:
        if zipfile.is_zipfile(archive):
            _extract_zip(archive, tmp, include)
        elif include is not None:
            raise ValueError(f"{archive.name} : extract_only n'est pris en charge que pour les ZIP")
        elif archive.suffix.lower() == ".rar":
            _extract_rar(archive, tmp)
        else:
            raise ValueError(f"format d'archive non pris en charge : {archive.name}")
        (tmp / ".extracted").write_text(archive.name, encoding="utf-8")
        shutil.rmtree(dest, ignore_errors=True)
        tmp.rename(dest)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return dest


def is_archive(path: Path) -> bool:
    return path.suffix.lower() in {".zip", ".rar"}


def fetch_source(
    source_id: str,
    source: Source,
    raw_dir: Path,
    interim_dir: Path,
    lock: LockFile,
    *,
    extract: bool = True,
    progress: bool = False,
) -> list[DownloadResult]:
    """Télécharge, vérifie et (par défaut) extrait toutes les archives d'une source."""
    session = _session_for(source.provider)
    results = [
        download_file(source_id, f, raw_dir, lock, session, progress=progress) for f in source.files
    ]
    write_manifest(source_id, source, results, raw_dir)
    if extract:
        for spec, result in zip(source.files, results, strict=True):
            if is_archive(result.path):
                extract_archive(
                    result.path, interim_dir / source_id / result.path.stem, spec.extract_only
                )
    return results
