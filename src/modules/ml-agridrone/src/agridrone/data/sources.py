"""Registre des sources de données, téléchargement idempotent et vérification d'intégrité.

* Chaque projet a son registre (``ble/configs/data/sources.yaml``,
  ``olivier/configs/data/sources.yaml``), qui décrit chaque source : licence, preuve de
  vérification, attribution, fichiers et sommes de contrôle publiées.
* :func:`download_file` télécharge en flux vers un fichier ``.part``, calcule md5 et
  sha256 au passage, vérifie taille et empreintes, puis renomme de façon atomique. Un
  fichier déjà présent et conforme n'est pas retéléchargé.
* Quand le fournisseur ne publie pas d'empreinte (Kaggle, GFZ), le premier
  téléchargement l'enregistre dans ``sources.lock.yaml`` (versionné) ; les suivants
  sont vérifiés contre elle.
* :func:`extract_archive` extrait ZIP, RAR et TAR (``.tar``, ``.tar.gz``, ``.tgz``) en
  refusant les chemins absolus, les remontées ``..`` et les liens symboliques.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
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
from agridrone.core.paths import Project

#: Licences jugées compatibles avec un usage commercial (identifiants SPDX ; GPL-3.0 :
#: copyleft, réutilisation commerciale possible sous ses conditions).
COMMERCIAL_LICENSES = frozenset(
    {"CC-BY-4.0", "CC0-1.0", "CDLA-Permissive-1.0", "MIT", "Apache-2.0", "GPL-3.0"}
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
    #: Dépôt git : ``url`` est celle du dépôt, ``name`` le dossier local, et le contenu
    #: est figé à ce commit (40 caractères hexadécimaux), dont l'empreinte garantit
    #: l'intégrité. Pour les dépôts de milliers de fichiers sans somme publiée.
    commit: str | None = None

    @model_validator(mode="after")
    def _check_commit(self) -> SourceFile:
        if self.commit is not None:
            if not re.fullmatch(r"[0-9a-f]{40}", self.commit):
                raise ValueError(f"{self.name} : commit git invalide {self.commit!r}")
            if self.md5 or self.sha256 or self.size is not None or self.extract_only:
                raise ValueError(f"{self.name} : un dépôt git n'a ni taille, ni empreinte")
        return self

    @field_validator("name")
    @classmethod
    def _plain_file_name(cls, value: str) -> str:
        if not value or "/" in value or "\\" in value or value in {".", ".."}:
            raise ValueError(f"nom de fichier invalide : {value!r}")
        return value


Status = Literal["retained", "candidate", "noncommercial", "manual", "excluded"]

#: Statuts dont les fichiers sont téléchargés par défaut (aucune option à passer : une
#: expérience doit se reproduire telle quelle).
DOWNLOADABLE: frozenset[str] = frozenset({"retained", "candidate", "noncommercial"})

#: Libellés des statuts dans ``LICENCES_DONNEES.txt``.
STATUS_LABELS: dict[str, tuple[str, str]] = {
    "retained": (
        "libre",
        "licence permissive (CC BY, CC0, MIT...) : réutilisation possible, même commerciale",
    ),
    "candidate": (
        "à confirmer",
        "licence permissive déclarée par le déposant, provenance à confirmer",
    ),
    "noncommercial": (
        "non commercial",
        "licence non commerciale ou inconnue : usage académique non commercial seulement",
    ),
    "manual": (
        "manuel",
        "à télécharger à la main (formulaire, compte, accord ou dépôt qui refuse les robots)",
    ),
    "excluded": ("écarté", "non téléchargé (re-publication ou compilation d'autres jeux)"),
}


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    task: Literal["classification", "detection", "segmentation", "regression"]
    status: Status
    license: str
    license_evidence: str
    attribution: str
    provider: Literal[
        "zenodo", "mendeley", "kaggle", "gfz", "dataverse", "figshare", "s3", "git", "url"
    ]
    homepage: str
    #: Conditions d'utilisation acceptées en téléchargeant (contrat, et non simple licence).
    terms: str | None = None
    notes: str = ""
    files: list[SourceFile] = Field(default_factory=list)
    #: Liste des fichiers dans un CSV à part (colonnes name, url, size, md5, sha256),
    #: relatif au registre : pour les sources de milliers de fichiers.
    files_manifest: str | None = None

    @property
    def downloadable(self) -> bool:
        return self.status in DOWNLOADABLE

    @model_validator(mode="after")
    def _check_status(self) -> Source:
        if self.status == "retained" and self.license not in COMMERCIAL_LICENSES:
            raise ValueError(
                f"licence {self.license!r} non permissive : statut 'noncommercial', "
                f"pas 'retained' (permissives : {', '.join(sorted(COMMERCIAL_LICENSES))})"
            )
        if self.status == "noncommercial" and self.license in COMMERCIAL_LICENSES:
            raise ValueError(
                f"licence {self.license!r} permissive : statut 'retained' ou 'candidate', "
                "pas 'noncommercial'"
            )
        if self.downloadable and not self.files:
            raise ValueError("une source téléchargeable doit lister ses fichiers")
        if not self.downloadable and self.files:
            raise ValueError(f"statut {self.status!r} : aucun fichier à télécharger attendu")
        return self


class Registry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sources: dict[str, Source]

    def selected(self, ids: list[str] | None = None) -> dict[str, Source]:
        """Sources à télécharger : ``ids`` explicites, sinon toutes les sources
        téléchargeables, quelle que soit leur licence. Les sources « manuel » et
        « écarté » n'ont pas de fichier."""
        if ids:
            unknown = [i for i in ids if i not in self.sources]
            if unknown:
                raise ConfigError(f"Sources inconnues : {', '.join(unknown)}")
            chosen = {i: self.sources[i] for i in ids}
            manual = [i for i, s in chosen.items() if not s.downloadable]
            if manual:
                raise ConfigError(
                    f"Sources sans téléchargement automatique : {', '.join(manual)} "
                    "(voir le fichier LICENCES_DONNEES.txt du projet)"
                )
            return chosen
        return {i: s for i, s in self.sources.items() if s.downloadable}


def licence_report(registry: Registry, project: Project, lock: LockFile | None = None) -> str:
    """Texte du fichier ``LICENCES_DONNEES.txt`` d'un projet : statut, licence, conditions
    et attribution de chaque source. Déterministe (aucune date) pour être versionné."""
    import textwrap

    def field(label: str, text: str) -> list[str]:
        return textwrap.wrap(
            " ".join(text.split()),
            width=92,
            initial_indent=f"  {label:<11} : ",
            subsequent_indent=" " * 16,
            break_on_hyphens=False,
            break_long_words=False,
        )

    titre = f"LICENCES DES DONNÉES : PROJET {project.title}"
    lines = [
        titre,
        "=" * len(titre),
        "",
        "Usage : projet académique, non commercial (confirmé le 12 octobre 2026).",
        "Toutes les sources téléchargeables du projet sont récupérées par défaut :",
        f"    uv run agridrone data download --project {project.name}",
        "",
        f"Fichier généré depuis {project.registry} par la commande",
        f"`uv run agridrone data licences --project {project.name}`",
        "(ne pas le modifier à la main).",
        "",
        "Statuts",
        "-------",
    ]
    lines += [f"  {label:<15} {text}" for label, text in STATUS_LABELS.values()]
    lines += [
        "",
        "Si le projet devenait commercial : ne garder que les sources « libre » (et « à",
        "confirmer » une fois la provenance établie), puis réentraîner les modèles sans les",
        "autres. Les licences CC BY imposent de citer les auteurs (ligne « Citer »).",
    ]
    lines += ["", "", "Sources", "======="]
    for source_id, src in registry.sources.items():
        sizes = [
            f.size or ((lock.get(f"{source_id}/{f.name}") or {}).get("size") if lock else None)
            for f in src.files
        ]
        lines += ["", f"{source_id} : {src.title}"]
        lines += field("Statut", STATUS_LABELS[src.status][0])
        lines += field("Licence", f"{src.license} ({src.license_evidence})")
        if src.terms:
            lines += field("Conditions", src.terms)
        lines += field("Citer", src.attribution)
        lines += field("Lien", src.homepage)
        if src.files:
            total = sum(s or 0 for s in sizes) / 1e9
            size = f"{total:.2f} Go".replace(".", ",")
            if None in sizes:
                size += " (+ fichiers de taille inconnue avant le premier téléchargement)"
            lines += field("Taille", f"{size}, {len(src.files)} fichier(s)")
        if src.notes:
            lines += field("Remarque", src.notes)
    return "\n".join(lines) + "\n"


def read_manifest_csv(path: Path) -> list[dict[str, Any]]:
    """Fichiers d'une source listés en CSV (name, url, size, md5, sha256)."""
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return [
        {
            "name": row["name"],
            "url": row["url"],
            "size": int(row["size"]) if row.get("size") else None,
            "md5": row.get("md5") or None,
            "sha256": row.get("sha256") or None,
        }
        for row in rows
    ]


def load_registry(path: str | Path) -> Registry:
    path = Path(path)
    data = load_yaml(path)
    for source_id, raw in (data.get("sources") or {}).items():
        manifest = raw.get("files_manifest") if isinstance(raw, dict) else None
        if manifest:
            if raw.get("files"):
                raise ConfigError(f"{source_id} : `files` et `files_manifest` sont exclusifs")
            raw["files"] = read_manifest_csv(path.parent / manifest)
    try:
        return Registry.model_validate(data)
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
    if file.commit is not None:
        return _git_checkout(file.url, file.commit, dest)
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


_GIT_MARKER = ".agridrone-commit"


def git_checkout_present(dest: Path, commit: str) -> bool:
    marker = dest / _GIT_MARKER
    return marker.is_file() and marker.read_text(encoding="utf-8").strip() == commit


def _git_checkout(url: str, commit: str, dest: Path) -> DownloadResult:
    """Récupère le dépôt ``url`` figé au commit ``commit`` dans ``dest`` (sans historique),
    vérifie le commit obtenu, puis renomme de façon atomique. Idempotent (marqueur)."""

    def size_of(root: Path) -> int:
        return sum(p.stat().st_size for p in root.rglob("*") if p.is_file())

    if git_checkout_present(dest, commit):
        return DownloadResult(dest, "present", Digests("", f"git:{commit}", size_of(dest)))
    git = shutil.which("git")
    if git is None:
        raise RuntimeError(f"{url} : git introuvable (https://git-scm.com/downloads)")
    tmp = dest.with_name(dest.name + ".part")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    try:

        def run(*args: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [git, "-C", str(tmp), *args], check=True, capture_output=True, text=True
            )

        run("init", "-q")
        run("fetch", "-q", "--depth", "1", url, commit)
        run("-c", "advice.detachedHead=false", "checkout", "-q", "FETCH_HEAD")
        head = run("rev-parse", "HEAD").stdout.strip()
        if head != commit:
            raise IntegrityError(f"{url} : commit attendu {commit}, obtenu {head}")
        shutil.rmtree(tmp / ".git")
        (tmp / _GIT_MARKER).write_text(commit, encoding="utf-8")
        shutil.rmtree(dest, ignore_errors=True)
        tmp.rename(dest)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return DownloadResult(dest, "downloaded", Digests("", f"git:{commit}", size_of(dest)))


def pending_bytes(source_id: str, source: Source, raw_dir: Path, lock: LockFile) -> int | None:
    """Octets restant à télécharger pour ``source`` (None si une taille est inconnue)."""
    total = 0
    for f in source.files:
        dest = raw_dir / source_id / f.name
        if f.commit is not None:
            if not git_checkout_present(dest, f.commit):
                return None
            continue
        if dest.exists():
            continue
        size = (
            f.size if f.size is not None else (lock.get(f"{source_id}/{f.name}") or {}).get("size")
        )
        if size is None:
            return None
        total += size
    return total


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
    # Aucun décodeur RAR ne lit toutes les archives : unar échoue sur certaines RAR 5
    # (jeu d'Uğuz et Uysal), bsdtar sur d'autres (erreurs CRC sur l'archive d'Éthiopie).
    # On essaie donc chaque outil disponible, en repartant d'un dossier vide.
    errors: list[str] = []
    for tool, command in _RAR_TOOLS:
        exe = find_tool(tool)
        if not exe:
            continue
        try:
            if tool == "bsdtar":  # seul outil dont on contrôle la liste avant extraction
                listing = subprocess.run(
                    [exe, "-tf", str(archive)], capture_output=True, text=True, check=True
                ).stdout.splitlines()
                for name in listing:
                    _check_member(name)
            subprocess.run(command(exe, archive, dest), check=True, capture_output=True)
            break
        except subprocess.CalledProcessError as exc:
            errors.append(f"{tool} (code {exc.returncode})")
            shutil.rmtree(dest, ignore_errors=True)
            dest.mkdir(parents=True)
    else:
        if errors:
            raise RuntimeError(
                f"{archive.name} : extraction RAR en échec avec " + ", ".join(errors)
            )
        raise RuntimeError(
            f"{archive.name} : aucun outil d'extraction RAR trouvé. Installer 7-Zip "
            "(Windows : https://www.7-zip.org), unar (apt install unar, brew install unar) "
            "ou unrar."
        )
    root = dest.resolve()
    for path in dest.rglob("*"):
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise UnsafeArchiveError(f"chemin refusé après extraction : {path}")


def _extract_tar(archive: Path, dest: Path) -> None:
    # Lecture en flux (une seule passe, même pour une archive .tar.gz de plusieurs dizaines
    # de Go) ; le filtre « data » refuse chemins absolus, remontées ``..``, liens sortant
    # de ``dest`` et fichiers spéciaux. La taille extraite n'étant connue qu'en fin de
    # lecture, l'espace libre est contrôlé avec la taille de l'archive (borne basse).
    _check_free_space(archive.stat().st_size, dest)
    with tarfile.open(archive, mode="r|*") as tf:
        for member in tf:
            _check_member(member.name)
            if member.issym() or member.islnk():
                raise UnsafeArchiveError(f"lien refusé : {member.name!r}")
            tf.extract(member, dest, filter="data")


def is_tar(path: Path) -> bool:
    name = path.name.lower()
    return name.endswith((".tar", ".tar.gz", ".tgz"))


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
        elif is_tar(archive):
            _extract_tar(archive, tmp)
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


def archive_stem(path: Path) -> str:
    """Nom du dossier d'extraction : le nom de l'archive sans ``.zip``, ``.rar``, ``.tar``,
    ``.tar.gz`` ni ``.tgz``."""
    name = path.name
    for suffix in (".tar.gz", ".tgz", ".tar", ".zip", ".rar"):
        if name.lower().endswith(suffix):
            return name[: -len(suffix)]
    return path.stem


def is_archive(path: Path) -> bool:
    return path.suffix.lower() in {".zip", ".rar"} or is_tar(path)


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
                    result.path,
                    interim_dir / source_id / archive_stem(result.path),
                    spec.extract_only,
                )
    return results
