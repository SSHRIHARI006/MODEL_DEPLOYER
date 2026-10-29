#!/usr/bin/env python3
"""Validation helpers for the restore shell script; no database or S3 side effects."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tarfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

MANIFEST_NAME = "manifest.json"


class BackupValidationError(ValueError):
    pass


def _safe_relative_path(value: str) -> PurePosixPath:
    if not value or "\\" in value or "\x00" in value:
        raise BackupValidationError(f"unsafe archive path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", "..") for part in path.parts):
        raise BackupValidationError(f"unsafe archive path: {value!r}")
    if path.parts and re.fullmatch(r"[A-Za-z]:.*", path.parts[0]):
        raise BackupValidationError(f"unsafe archive path: {value!r}")
    return path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def validate_manifest(backup_dir: Path) -> dict:
    backup_root = backup_dir.resolve()
    manifest_path = backup_root / MANIFEST_NAME
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise BackupValidationError("backup manifest is missing")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BackupValidationError("backup manifest is invalid") from exc
    if not isinstance(manifest, dict) or manifest.get("format_version") != 1:
        raise BackupValidationError("unsupported backup manifest format")
    expected_files = manifest.get("files")
    if not isinstance(expected_files, dict) or not expected_files:
        raise BackupValidationError("backup manifest has no file checksums")
    for name, expected_hash in expected_files.items():
        rel = _safe_relative_path(name)
        if not re.fullmatch(r"[0-9a-f]{64}", str(expected_hash)):
            raise BackupValidationError(f"invalid checksum for {name!r}")
        path = backup_root.joinpath(*rel.parts)
        if path.is_symlink() or not path.is_file():
            raise BackupValidationError(f"backup component is missing: {name}")
        try:
            path.resolve().relative_to(backup_root)
        except ValueError as exc:
            raise BackupValidationError(f"backup component escapes backup directory: {name}") from exc
        actual = _sha256_file(path)
        if actual != expected_hash:
            raise BackupValidationError(f"checksum mismatch: {name}")
    return manifest


def validate_storage_archive(archive_path: Path) -> list[tarfile.TarInfo]:
    try:
        with tarfile.open(archive_path, "r:gz") as archive:
            members = archive.getmembers()
    except (OSError, tarfile.TarError) as exc:
        raise BackupValidationError("storage archive is invalid") from exc
    seen: set[str] = set()
    if len(members) > 100_000:
        raise BackupValidationError("storage archive has too many entries")
    total_size = 0
    for member in members:
        name = member.name.rstrip("/")
        if name in ("", "."):
            continue
        rel = _safe_relative_path(name)
        normalized = rel.as_posix()
        if normalized in seen:
            raise BackupValidationError(f"duplicate archive entry: {normalized}")
        seen.add(normalized)
        if not (member.isdir() or member.isreg()):
            raise BackupValidationError(f"unsupported archive entry type: {normalized}")
        if member.size < 0:
            raise BackupValidationError(f"invalid archive entry size: {normalized}")
        total_size += member.size
        if total_size > 100 * 1024 * 1024 * 1024:
            raise BackupValidationError("storage archive exceeds the 100 GiB extraction limit")
    return members


def extract_storage_archive(archive_path: Path, destination: Path) -> list[Path]:
    members = validate_storage_archive(archive_path)
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    extracted: list[Path] = []
    with tarfile.open(archive_path, "r:gz") as archive:
        for member in members:
            if member.name.rstrip("/") in ("", "."):
                continue
            rel = _safe_relative_path(member.name.rstrip("/"))
            target = destination.joinpath(*rel.parts)
            resolved = target.resolve()
            try:
                resolved.relative_to(root)
            except ValueError as exc:
                raise BackupValidationError(f"archive path escapes extraction directory: {member.name}") from exc
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    raise BackupValidationError(f"cannot read archive entry: {member.name}")
                with source, target.open("xb") as output:
                    while block := source.read(1024 * 1024):
                        output.write(block)
            extracted.append(target)
    return extracted


def verify_archive_manifest(backup_dir: Path, members: list[tarfile.TarInfo]) -> None:
    manifest = validate_manifest(backup_dir)
    if "storage.tar.gz" not in manifest["files"]:
        return
    actual_names = {
        member.name.rstrip("/").removeprefix("./")
        for member in members
        if member.isfile() and member.name.rstrip("/") not in ("", ".")
    }
    expected = manifest.get("storage_objects")
    if expected is not None and (not isinstance(expected, list) or set(expected) != actual_names):
        raise BackupValidationError("storage object manifest does not match archive entries")


def upload_storage_objects(root: Path, bucket: str, s3_client) -> int:
    count = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        key = path.relative_to(root).as_posix()
        s3_client.upload_file(str(path), bucket, key)
        count += 1
    return count


def create_manifest(backup_dir: Path, database: str, storage_objects: list[str] | None = None) -> dict:
    files = {}
    for name in ("postgres.dump", "storage.tar.gz"):
        path = backup_dir / name
        if not path.is_file() or path.stat().st_size == 0:
            raise BackupValidationError(f"required backup component is missing or empty: {name}")
        files[name] = _sha256_file(path)
    manifest = {
        "format_version": 1,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": database,
        "files": files,
        "storage_objects": sorted(storage_objects or []),
    }
    (backup_dir / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create-manifest")
    create.add_argument("backup_dir", type=Path)
    create.add_argument("database")
    validate = subparsers.add_parser("validate")
    validate.add_argument("backup_dir", type=Path)
    extract = subparsers.add_parser("extract")
    extract.add_argument("archive", type=Path)
    extract.add_argument("destination", type=Path)
    upload = subparsers.add_parser("upload")
    upload.add_argument("root", type=Path)
    upload.add_argument("bucket")
    args = parser.parse_args()
    if args.command == "create-manifest":
        create_manifest(args.backup_dir, args.database)
    elif args.command == "validate":
        manifest = validate_manifest(args.backup_dir)
        required = {"postgres.dump", "storage.tar.gz"}
        if set(manifest["files"]) != required:
            raise BackupValidationError("backup manifest must checksum postgres.dump and storage.tar.gz only")
        members = validate_storage_archive(args.backup_dir / "storage.tar.gz")
        verify_archive_manifest(args.backup_dir, members)
        if not isinstance(manifest.get("database"), str) or not manifest["database"]:
            raise BackupValidationError("backup manifest database is missing")
        storage_objects = manifest.get("storage_objects")
        if not isinstance(storage_objects, list) or any(not isinstance(key, str) for key in storage_objects):
            raise BackupValidationError("backup manifest storage_objects must be a list of keys")
    elif args.command == "extract":
        extract_storage_archive(args.archive, args.destination)
    else:
        import boto3
        from botocore.client import Config

        s3 = boto3.client(
            "s3",
            endpoint_url=os.environ.get("AWS_S3_ENDPOINT_URL", "http://localhost:9000"),
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "minioadmin"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "minioadmin"),
            use_ssl=os.environ.get("AWS_S3_USE_SSL", "false").lower() == "true",
            config=Config(s3={"addressing_style": "path"}, connect_timeout=3, retries={"max_attempts": 1}),
        )
        try:
            s3.head_bucket(Bucket=args.bucket)
        except Exception as exc:
            raise BackupValidationError(f"required object bucket is not available: {args.bucket}") from exc
        count = upload_storage_objects(args.root, args.bucket, s3)
        print(f"Restored {count} objects to bucket {args.bucket}")


if __name__ == "__main__":
    main()
