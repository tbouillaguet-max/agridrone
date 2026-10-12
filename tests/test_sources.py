from __future__ import annotations

import hashlib
import threading
import zipfile
from collections.abc import Iterator
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

import pytest
import requests

from agridrone.core.config import ConfigError
from agridrone.data.sources import (
    COMMERCIAL_LICENSES,
    IntegrityError,
    LockFile,
    Registry,
    Source,
    SourceFile,
    UnsafeArchiveError,
    download_file,
    extract_archive,
    fetch_source,
    load_registry,
)

PAYLOAD = b"donnees de test " * 1000


class _CountingHandler(SimpleHTTPRequestHandler):
    hits: ClassVar[dict[str, int]] = {}

    def do_GET(self) -> None:
        _CountingHandler.hits[self.path] = _CountingHandler.hits.get(self.path, 0) + 1
        super().do_GET()

    def log_message(self, *args: object) -> None:  # silence
        pass


@pytest.fixture
def server(tmp_path: Path) -> Iterator[tuple[str, Path]]:
    """Serveur HTTP local servant ``tmp_path/www``."""
    root = tmp_path / "www"
    root.mkdir()
    _CountingHandler.hits = {}
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), partial(_CountingHandler, directory=str(root)))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", root
    httpd.shutdown()


def _source(files: list[SourceFile], **extra: object) -> Source:
    base = {
        "title": "test",
        "project": "wheat",
        "task": "classification",
        "status": "retained",
        "license": "CC-BY-4.0",
        "license_evidence": "test",
        "attribution": "test",
        "provider": "url",
        "homepage": "http://example.invalid",
        "files": files,
    }
    return Source.model_validate({**base, **extra})


def test_download_verifies_md5_and_is_idempotent(server: tuple[str, Path], tmp_path: Path) -> None:
    url, root = server
    (root / "a.bin").write_bytes(PAYLOAD)
    file = SourceFile(
        name="a.bin", url=f"{url}/a.bin", size=len(PAYLOAD), md5=hashlib.md5(PAYLOAD).hexdigest()
    )
    lock = LockFile(tmp_path / "lock.yaml")
    session = requests.Session()

    first = download_file("src", file, tmp_path / "raw", lock, session)
    assert first.status == "downloaded"
    assert first.path.read_bytes() == PAYLOAD
    second = download_file("src", file, tmp_path / "raw", lock, session)
    assert second.status == "present"
    assert _CountingHandler.hits["/a.bin"] == 1  # pas de second téléchargement
    assert not lock.entries  # md5 publiée : rien à enregistrer


def test_bad_checksum_leaves_no_file(server: tuple[str, Path], tmp_path: Path) -> None:
    url, root = server
    (root / "a.bin").write_bytes(PAYLOAD)
    file = SourceFile(name="a.bin", url=f"{url}/a.bin", sha256="0" * 64)
    with pytest.raises(IntegrityError, match="sha256"):
        download_file(
            "src", file, tmp_path / "raw", LockFile(tmp_path / "l.yaml"), requests.Session()
        )
    assert not list((tmp_path / "raw" / "src").iterdir())  # ni fichier final ni .part


def test_trust_on_first_use_then_detects_change(server: tuple[str, Path], tmp_path: Path) -> None:
    url, root = server
    (root / "k.zip").write_bytes(PAYLOAD)
    file = SourceFile(name="k.zip", url=f"{url}/k.zip")  # aucune empreinte publiée
    lock_path = tmp_path / "lock.yaml"
    download_file("src", file, tmp_path / "raw", LockFile(lock_path), requests.Session())
    entry = LockFile(lock_path).get("src/k.zip")
    assert entry == {"sha256": hashlib.sha256(PAYLOAD).hexdigest(), "size": len(PAYLOAD)}

    # Le fichier local est corrompu : détecté grâce au verrou, pas de retéléchargement silencieux.
    (tmp_path / "raw" / "src" / "k.zip").write_bytes(b"corrompu")
    with pytest.raises(IntegrityError, match="non conforme"):
        download_file("src", file, tmp_path / "raw", LockFile(lock_path), requests.Session())


def test_http_error_propagates(server: tuple[str, Path], tmp_path: Path) -> None:
    url, _ = server
    file = SourceFile(name="absent.bin", url=f"{url}/absent.bin")
    with pytest.raises(requests.HTTPError):
        download_file(
            "src", file, tmp_path / "raw", LockFile(tmp_path / "l.yaml"), requests.Session()
        )


def _zip(path: Path, members: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return path


def test_extract_zip_is_atomic_and_idempotent(tmp_path: Path) -> None:
    archive = _zip(tmp_path / "a.zip", {"train/healthy/1.jpg": b"x", "README.txt": b"y"})
    dest = extract_archive(archive, tmp_path / "out")
    assert (dest / "train" / "healthy" / "1.jpg").read_bytes() == b"x"
    (dest / "README.txt").write_bytes(b"modifie")
    extract_archive(archive, tmp_path / "out")  # marqueur présent : pas de réextraction
    assert (dest / "README.txt").read_bytes() == b"modifie"
    assert not (tmp_path / "out.tmp").exists()


@pytest.mark.parametrize("bad", ["../evil.txt", "/abs/evil.txt", "a/../../evil.txt"])
def test_extract_rejects_path_traversal(tmp_path: Path, bad: str) -> None:
    archive = _zip(tmp_path / "bad.zip", {"ok.txt": b"1", bad: b"2"})
    with pytest.raises(UnsafeArchiveError):
        extract_archive(archive, tmp_path / "out")
    assert not (tmp_path / "out").exists()
    assert not (tmp_path / "evil.txt").exists()


def test_fetch_source_downloads_extracts_and_writes_manifest(
    server: tuple[str, Path], tmp_path: Path
) -> None:
    url, root = server
    _zip(root / "d.zip", {"img/1.jpg": b"img"})
    src = _source([SourceFile(name="d.zip", url=f"{url}/d.zip")])
    fetch_source("demo", src, tmp_path / "raw", tmp_path / "interim", LockFile(tmp_path / "l.yaml"))
    assert (tmp_path / "interim" / "demo" / "d" / "img" / "1.jpg").read_bytes() == b"img"
    manifest = (tmp_path / "raw" / "demo" / "SOURCE.json").read_text(encoding="utf-8")
    assert "CC-BY-4.0" in manifest


def test_registry_rules() -> None:
    with pytest.raises(ValueError, match="non permissive"):
        _source([SourceFile(name="a", url="http://x")], license="CC-BY-NC-4.0")
    with pytest.raises(ValueError, match="permissive : statut"):
        _source([SourceFile(name="n", url="http://x")], status="noncommercial")
    with pytest.raises(ValueError, match="lister ses fichiers"):
        _source([])
    with pytest.raises(ValueError, match="aucun fichier"):
        _source([SourceFile(name="a", url="http://x")], status="manual", license="x")
    assert _source([], status="excluded", license="LicenseRef-x").status == "excluded"
    with pytest.raises(ValueError, match="nom de fichier"):
        SourceFile(name="../a.zip", url="http://x")


def test_everything_downloadable_is_selected_by_default() -> None:
    # Projet académique : aucune option à passer pour reproduire une expérience.
    registry = Registry(
        sources={
            "ok": _source([SourceFile(name="a", url="http://x")]),
            "cand": _source([SourceFile(name="b", url="http://x")], status="candidate"),
            "nc": _source(
                [SourceFile(name="n", url="http://x")],
                status="noncommercial",
                license="CC-BY-NC-4.0",
            ),
            "form": _source([], status="manual", license="LicenseRef-x"),
            "ko": _source([], status="excluded", license="LicenseRef-x"),
        }
    )
    assert list(registry.selected()) == ["ok", "cand", "nc"]
    assert list(registry.selected(["nc"])) == ["nc"]
    with pytest.raises(ConfigError, match="sans téléchargement automatique"):
        registry.selected(["form"])
    with pytest.raises(ConfigError, match="inconnues"):
        registry.selected(["nope"])


def test_licence_report_lists_every_source_by_project() -> None:
    from agridrone.data.sources import licence_report

    registry = Registry(
        sources={
            "ble": _source([SourceFile(name="a", url="http://x", size=2_500_000_000)]),
            "olive_nc": _source(
                [SourceFile(name="b", url="http://x")],
                project="olive",
                status="noncommercial",
                license="CC-BY-NC-4.0",
                terms="https://example.invalid/terms.pdf",
            ),
        }
    )
    text = licence_report(registry)
    assert text.index("BLÉ") < text.index("ble : test") < text.index("OLIVIER")
    assert text.index("OLIVIER") < text.index("olive_nc : test")
    assert "non commercial" in text and "https://example.invalid/terms.pdf" in text
    assert "2,50 Go, 1 fichier(s)" in text and "taille inconnue" in text
    assert licence_report(registry) == text  # déterministe : versionnable


def test_extract_tar_gz_is_safe(tmp_path: Path) -> None:
    import io
    import tarfile

    from agridrone.data.sources import archive_stem, is_archive

    def add(tf: tarfile.TarFile, name: str, data: bytes = b"x") -> None:
        info = tarfile.TarInfo(name)
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))

    archive = tmp_path / "jeu-2021.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        add(tf, "jeu/train/images/a.jpg", b"image")
        add(tf, "jeu/train/labels/a.png", b"masque")
    assert is_archive(archive) and archive_stem(archive) == "jeu-2021"
    dest = extract_archive(archive, tmp_path / "out")
    assert (dest / "jeu" / "train" / "images" / "a.jpg").read_bytes() == b"image"
    assert extract_archive(archive, tmp_path / "out") == dest  # idempotent

    for bad, kind in (("../evil.txt", None), ("lien", tarfile.SYMTYPE)):
        evil = tmp_path / "evil.tar"
        with tarfile.open(evil, "w") as tf:
            if kind is None:
                add(tf, bad)
            else:
                info = tarfile.TarInfo(bad)
                info.type, info.linkname = kind, "/etc/passwd"
                tf.addfile(info)
        with pytest.raises(UnsafeArchiveError):
            extract_archive(evil, tmp_path / f"evil_out_{bad[-4:]}")
        assert not (tmp_path / f"evil_out_{bad[-4:]}").exists()


def test_registry_selects_by_project() -> None:
    registry = Registry(
        sources={
            "ble": _source([SourceFile(name="a", url="http://x")]),
            "olive": _source([SourceFile(name="b", url="http://x")], project="olive"),
            "olive_cand": _source(
                [SourceFile(name="c", url="http://x")], project="olive", status="candidate"
            ),
        }
    )
    assert list(registry.selected()) == ["ble", "olive", "olive_cand"]
    assert list(registry.selected(None, "olive")) == ["olive", "olive_cand"]
    assert list(registry.selected(None, "wheat")) == ["ble"]
    with pytest.raises(ValueError):
        _source([SourceFile(name="a", url="http://x")], project="vigne")


def test_find_tool_looks_for_7zip_and_tar_on_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from agridrone.data import sources

    exe = tmp_path / "7-Zip" / "7z.exe"
    exe.parent.mkdir()
    exe.write_bytes(b"")
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path))
    monkeypatch.delenv("PROGRAMFILES(X86)", raising=False)
    monkeypatch.setattr(
        sources.shutil,
        "which",
        lambda name: "C:/Windows/System32/tar.exe" if name == "tar" else None,
    )
    assert sources.find_tool("7z", windows=True) == str(exe)
    assert sources.find_tool("bsdtar", windows=True) == "C:/Windows/System32/tar.exe"
    assert sources.find_tool("unar", windows=True) is None
    assert sources.find_tool("7z", windows=False) is None  # hors Windows : le PATH seulement


def test_repository_registry_is_valid(repo_root: Path) -> None:
    registry = load_registry(repo_root / "configs" / "data" / "sources.yaml")
    retained = {k: s for k, s in registry.sources.items() if s.status == "retained"}
    assert retained, "au moins une source retenue"
    assert all(s.license in COMMERCIAL_LICENSES for s in retained.values())
    for source_id, source in registry.sources.items():
        names = [f.name for f in source.files]
        assert len(names) == len(set(names)), source_id
        for f in source.files:
            assert f.url.startswith("https://")


def test_licence_file_is_up_to_date(repo_root: Path) -> None:
    from agridrone.data.sources import licence_report

    registry = load_registry(repo_root / "configs" / "data" / "sources.yaml")
    lock = LockFile(repo_root / "configs" / "data" / "sources.lock.yaml")
    committed = (repo_root / "LICENCES_DONNEES.txt").read_text(encoding="utf-8")
    assert committed == licence_report(registry, lock), (
        "LICENCES_DONNEES.txt n'est plus à jour : uv run agridrone data licences"
    )


def test_extract_only_keeps_matching_members(tmp_path: Path) -> None:
    from agridrone.data.sources import extract_archive

    archive = tmp_path / "a.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("Data/Original Dataset/Healthy/a.jpg", b"1")
        zf.writestr("Data/Augmented Dataset/Healthy/a_aug.jpg", b"2")
    dest = extract_archive(archive, tmp_path / "out", ["*/Original Dataset/*"])
    files = sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file())
    assert files == [".extracted", "Data/Original Dataset/Healthy/a.jpg"]
    with pytest.raises(ValueError, match="aucun membre"):
        extract_archive(archive, tmp_path / "out2", ["*/Nope/*"])


def _git(*args: str, cwd: Path) -> str:
    import subprocess

    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def test_git_source_is_pinned_to_a_commit(tmp_path: Path) -> None:
    import shutil

    if shutil.which("git") is None:
        pytest.skip("git absent")
    repo = tmp_path / "repo"
    repo.mkdir()
    _git("init", "-q", cwd=repo)
    _git("config", "uploadpack.allowReachableSHA1InWant", "true", cwd=repo)
    (repo / "images").mkdir()
    (repo / "images" / "a.jpg").write_bytes(b"image a")
    _git("add", ".", cwd=repo)
    _git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "v1", cwd=repo)
    first = _git("rev-parse", "HEAD", cwd=repo)
    (repo / "images" / "b.jpg").write_bytes(b"image b")  # commit suivant : ignoré
    _git("add", ".", cwd=repo)
    _git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "v2", cwd=repo)

    spec = SourceFile(name="depot", url=repo.as_uri(), commit=first)
    source = _source([spec], status="noncommercial", license="LicenseRef-none")
    lock = LockFile(tmp_path / "lock.yaml")
    results = fetch_source("gh", source, tmp_path / "raw", tmp_path / "interim", lock)
    dest = tmp_path / "raw" / "gh" / "depot"
    assert results[0].status == "downloaded" and results[0].digests.sha256 == f"git:{first}"
    assert (dest / "images" / "a.jpg").read_bytes() == b"image a"
    assert not (dest / "images" / "b.jpg").exists() and not (dest / ".git").exists()
    again = fetch_source("gh", source, tmp_path / "raw", tmp_path / "interim", lock)
    assert again[0].status == "present"
    assert lock.entries == {}  # l'empreinte est le commit : rien à enregistrer

    with pytest.raises(ValueError, match="commit git invalide"):
        SourceFile(name="d", url="https://x", commit="main")
    with pytest.raises(ValueError, match="ni taille"):
        SourceFile(name="d", url="https://x", commit=first, size=3)


def test_files_manifest_and_pending_bytes(tmp_path: Path) -> None:
    from agridrone.data.sources import pending_bytes

    (tmp_path / "manifests").mkdir()
    (tmp_path / "manifests" / "big.csv").write_text(
        "name,url,size,md5,sha256\n"
        "a.jpg,https://example.invalid/a,100,,aa\n"
        "b.jpg,https://example.invalid/b,250,,bb\n",
        encoding="utf-8",
    )
    (tmp_path / "sources.yaml").write_text(
        """
sources:
  big:
    title: t
    project: olive
    task: detection
    status: retained
    license: CC-BY-4.0
    license_evidence: e
    attribution: a
    provider: mendeley
    homepage: https://example.invalid
    files_manifest: manifests/big.csv
""",
        encoding="utf-8",
    )
    registry = load_registry(tmp_path / "sources.yaml")
    files = registry.sources["big"].files
    assert [(f.name, f.size, f.sha256) for f in files] == [
        ("a.jpg", 100, "aa"),
        ("b.jpg", 250, "bb"),
    ]

    raw, lock = tmp_path / "raw", LockFile(tmp_path / "lock.yaml")
    assert pending_bytes("big", registry.sources["big"], raw, lock) == 350
    (raw / "big").mkdir(parents=True)
    (raw / "big" / "a.jpg").write_bytes(b"x")
    assert pending_bytes("big", registry.sources["big"], raw, lock) == 250
    unknown = _source([SourceFile(name="k.zip", url="https://x")])
    assert pending_bytes("k", unknown, raw, lock) is None


def test_rar_extraction_falls_back_to_next_tool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys

    from agridrone.data import sources

    partial = (
        "import sys, pathlib; (pathlib.Path(sys.argv[1]) / 'partiel').write_text('x'); sys.exit(1)"
    )
    good = "import sys, pathlib; (pathlib.Path(sys.argv[1]) / 'ok.jpg').write_text('image')"
    monkeypatch.setattr(
        sources,
        "_RAR_TOOLS",
        (
            ("casse", lambda exe, a, d: [exe, "-c", partial, str(d)]),
            ("absent", lambda exe, a, d: [exe, "-c", good, str(d)]),
            ("bon", lambda exe, a, d: [exe, "-c", good, str(d)]),
        ),
    )
    monkeypatch.setattr(
        sources, "find_tool", lambda name: None if name == "absent" else sys.executable
    )
    archive = tmp_path / "jeu.rar"
    archive.write_bytes(b"Rar!")
    dest = extract_archive(archive, tmp_path / "out")
    assert sorted(p.name for p in dest.iterdir()) == [".extracted", "ok.jpg"]  # rien du 1er essai

    monkeypatch.setattr(sources, "_RAR_TOOLS", sources._RAR_TOOLS[:1])
    with pytest.raises(RuntimeError, match="casse"):
        extract_archive(archive, tmp_path / "out2")
