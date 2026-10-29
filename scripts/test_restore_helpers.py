from __future__ import annotations

import hashlib
import json
import os
import subprocess
import io
import tarfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.restore_helpers import (
    BackupValidationError,
    extract_storage_archive,
    validate_manifest,
    validate_storage_archive,
)


def _backup(tmp_path: Path, contents: dict[str, bytes]) -> Path:
    backup = tmp_path / "backup"
    backup.mkdir()
    hashes = {}
    for name, data in contents.items():
        path = backup / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        hashes[name] = hashlib.sha256(data).hexdigest()
    (backup / "manifest.json").write_text(
        json.dumps({"format_version": 1, "files": hashes}), encoding="utf-8"
    )
    return backup


def _tar(path: Path, name: str, content: bytes = b"payload") -> None:
    with tarfile.open(path, "w:gz") as archive:
        info = tarfile.TarInfo(name)
        info.size = len(content)
        archive.addfile(info, io.BytesIO(content))


def test_manifest_checksums_validate(tmp_path):
    backup = _backup(tmp_path, {"postgres.dump": b"dump", "storage.tar.gz": b"archive"})
    manifest = validate_manifest(backup)
    assert manifest["format_version"] == 1


def test_manifest_rejects_tampered_backup_component(tmp_path):
    backup = _backup(tmp_path, {"postgres.dump": b"dump"})
    (backup / "postgres.dump").write_bytes(b"tampered")
    with pytest.raises(BackupValidationError, match="checksum mismatch"):
        validate_manifest(backup)


def test_manifest_requires_all_expected_files(tmp_path):
    backup = tmp_path / "backup"
    backup.mkdir()
    (backup / "manifest.json").write_text(
        json.dumps({"format_version": 1, "files": {"postgres.dump": "0" * 64}})
    )
    with pytest.raises(BackupValidationError, match="missing"):
        validate_manifest(backup)


@pytest.mark.parametrize("name", ["../escape", "/absolute", "a/../../escape", "C:/escape", "..\\escape"])
def test_tar_rejects_unsafe_paths(tmp_path, name):
    archive = tmp_path / "storage.tar.gz"
    _tar(archive, name)
    with pytest.raises(BackupValidationError, match="unsafe archive path"):
        validate_storage_archive(archive)
    assert not (tmp_path.parent / "escape").exists()


def test_tar_rejects_symlinks_and_special_entries(tmp_path):
    archive_path = tmp_path / "storage.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        link = tarfile.TarInfo("link")
        link.type = tarfile.SYMTYPE
        link.linkname = "../../escape"
        archive.addfile(link)
    with pytest.raises(BackupValidationError, match="unsupported archive entry type"):
        validate_storage_archive(archive_path)


def test_safe_archive_extracts_regular_file(tmp_path):
    archive = tmp_path / "storage.tar.gz"
    _tar(archive, "nested/object.bin", b"payload")
    extracted = extract_storage_archive(archive, tmp_path / "out")
    assert (tmp_path / "out/nested/object.bin").read_bytes() == b"payload"
    assert len(extracted) == 1


def test_restore_script_propagates_database_and_storage_failures(tmp_path):
    backup = _backup(tmp_path, {"postgres.dump": b"dump", "storage.tar.gz": b"archive"})
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    commands = bin_dir / "commands.log"
    executable = bin_dir / "pg_restore"
    executable.write_text(
        "#!/bin/sh\n"
        'echo pg_restore >> "$COMMANDS_LOG"\n'
        "exit 17\n"
    )
    executable.chmod(0o755)
    # Validation helper invocation uses the real interpreter before the fake pg_restore.
    (backup / "storage.tar.gz").write_bytes(b"x")
    (backup / "manifest.json").write_text(json.dumps({
        "format_version": 1,
        "database": "testdb",
        "files": {
            "postgres.dump": hashlib.sha256(b"dump").hexdigest(),
            "storage.tar.gz": hashlib.sha256(b"x").hexdigest(),
        },
    }))
    (backup / "storage.tar.gz").unlink()
    _tar(backup / "storage.tar.gz", "object.bin")
    (backup / "manifest.json").write_text(json.dumps({
        "format_version": 1,
        "database": "testdb",
        "files": {
            "postgres.dump": hashlib.sha256(b"dump").hexdigest(),
            "storage.tar.gz": hashlib.sha256((backup / "storage.tar.gz").read_bytes()).hexdigest(),
        },
        "storage_objects": ["object.bin"],
    }))

    result = subprocess.run(
        ["bash", "scripts/restore.sh", str(backup)],
        env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}",
             "COMMANDS_LOG": str(commands), "RESTORE_CONFIRM": "YES", "RESTORE_DB": "disposable_test"},
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "SUCCESS" not in result.stdout
    assert commands.exists()
    assert commands.read_text().splitlines() == ["pg_restore"]


def test_upload_storage_objects_propagates_object_store_errors(tmp_path):
    from scripts.restore_helpers import upload_storage_objects

    root = tmp_path / "objects"
    root.mkdir()
    (root / "object.bin").write_bytes(b"data")
    s3 = MagicMock()
    s3.upload_file.side_effect = RuntimeError("storage unavailable")

    with pytest.raises(RuntimeError, match="storage unavailable"):
        upload_storage_objects(root, "disposable-test-bucket", s3)

    s3.upload_file.assert_called_once_with(str(root / "object.bin"), "disposable-test-bucket", "object.bin")
