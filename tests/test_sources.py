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
    with pytest.raises(ValueError, match="incompatible"):
        _source([SourceFile(name="a", url="http://x")], license="CC-BY-NC-4.0")
    with pytest.raises(ValueError, match="lister ses fichiers"):
        _source([])
    assert _source([], status="excluded", license="LicenseRef-x").status == "excluded"
    with pytest.raises(ValueError, match="nom de fichier"):
        SourceFile(name="../a.zip", url="http://x")

    registry = Registry(
        sources={
            "ok": _source([SourceFile(name="a", url="http://x")]),
            "cand": _source([SourceFile(name="b", url="http://x")], status="candidate"),
            "ko": _source([], status="excluded", license="LicenseRef-x"),
        }
    )
    assert list(registry.selected(None, include_candidates=False)) == ["ok"]
    assert list(registry.selected(None, include_candidates=True)) == ["ok", "cand"]
    with pytest.raises(ConfigError, match="exclues"):
        registry.selected(["ko"], include_candidates=False)


def test_repository_registry_is_valid(repo_root: Path) -> None:
    registry = load_registry(repo_root / "configs" / "data" / "sources.yaml")
    retained = {k: s for k, s in registry.sources.items() if s.status == "retained"}
    assert retained, "au moins une source retenue"
    assert all(s.license in COMMERCIAL_LICENSES for s in retained.values())
    for source in registry.sources.values():
        for f in source.files:
            assert f.url.startswith("https://")


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
