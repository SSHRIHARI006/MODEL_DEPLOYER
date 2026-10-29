"""Safe ZIP extraction for uploaded model bundles (SEC-04).

An uploaded archive is attacker-controlled input: it can be a ZIP bomb, use
absolute or ``..`` entry names, hide symlinks or device nodes, or carry a
manifest whose paths point outside the bundle. Nothing here trusts archive
metadata beyond the checks below, and every rejection path leaves no extracted
files behind.
"""

from __future__ import annotations

import re
import shutil
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

__all__ = [
    "ArchiveError",
    "ArchiveLimits",
    "resolve_declared_path",
    "safe_extract_zip",
]

_CHUNK_SIZE = 1024 * 1024
_WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:")
# File-type bits that must never appear in a model bundle.
_SPECIAL_FILE_TYPES = frozenset(
    {stat.S_IFCHR, stat.S_IFBLK, stat.S_IFIFO, stat.S_IFSOCK, stat.S_IFLNK}
)


class ArchiveError(ValueError):
    """The archive is unsafe, malformed, or exceeds the configured limits."""


@dataclass(frozen=True)
class ArchiveLimits:
    max_uncompressed_bytes: int
    max_entry_bytes: int
    max_entries: int
    max_path_length: int
    max_compression_ratio: float | None = None

    @classmethod
    def from_settings(cls) -> "ArchiveLimits":
        ratio = float(getattr(settings, "MAX_MODEL_COMPRESSION_RATIO", 0) or 0)
        return cls(
            max_uncompressed_bytes=int(
                getattr(settings, "MAX_MODEL_UNCOMPRESSED_BYTES", 200 * 1024 * 1024)
            ),
            max_entry_bytes=int(
                getattr(settings, "MAX_MODEL_ENTRY_BYTES", 50 * 1024 * 1024)
            ),
            max_entries=int(getattr(settings, "MAX_MODEL_ARCHIVE_ENTRIES", 512)),
            max_path_length=int(getattr(settings, "MAX_MODEL_PATH_LENGTH", 200)),
            max_compression_ratio=ratio if ratio > 0 else None,
        )


def _normalise_entry_path(name: str, limits: ArchiveLimits, *, label: str) -> str:
    """Return a safe relative path for an archive entry, or raise."""
    if not isinstance(name, str) or not name.strip():
        raise ArchiveError(f"{label} has no name")

    if len(name) > limits.max_path_length:
        raise ArchiveError(
            f"{label} path is longer than {limits.max_path_length} characters"
        )

    if name.startswith(("/", "\\")) or _WINDOWS_ABSOLUTE.match(name):
        raise ArchiveError(f"{label} uses an absolute path: {name!r}")

    parts = [part for part in name.replace("\\", "/").split("/") if part not in ("", ".")]
    if not parts:
        raise ArchiveError(f"{label} has no usable path: {name!r}")
    if any(part == ".." for part in parts):
        raise ArchiveError(f"{label} escapes the bundle directory: {name!r}")

    return "/".join(parts)


def _reject_special_file(info: zipfile.ZipInfo) -> None:
    mode = info.external_attr >> 16
    # mode == 0 means the archiver recorded no attributes; do not reject those.
    if mode and stat.S_IFMT(mode) in _SPECIAL_FILE_TYPES:
        raise ArchiveError(
            f"archive entry {info.filename!r} is not a regular file"
        )


def _validate_entries(
    archive: zipfile.ZipFile,
    limits: ArchiveLimits,
    required_files: tuple[str, ...],
) -> list[tuple[zipfile.ZipInfo, str]]:
    infos = archive.infolist()

    if len(infos) > limits.max_entries:
        raise ArchiveError(
            f"archive has {len(infos)} entries, more than the limit of "
            f"{limits.max_entries}"
        )

    entries: list[tuple[zipfile.ZipInfo, str]] = []
    declared_total = 0
    names: set[str] = set()

    for info in infos:
        _reject_special_file(info)
        relative = _normalise_entry_path(info.filename, limits, label="archive entry")
        names.add(relative)

        if info.is_dir():
            continue

        if info.file_size > limits.max_entry_bytes:
            raise ArchiveError(
                f"archive entry {relative!r} is larger than the per-file limit of "
                f"{limits.max_entry_bytes} bytes"
            )

        declared_total += info.file_size
        if declared_total > limits.max_uncompressed_bytes:
            raise ArchiveError(
                "archive expands to more than the configured uncompressed size limit "
                f"of {limits.max_uncompressed_bytes} bytes"
            )

        if limits.max_compression_ratio is not None:
            if info.compress_size <= 0:
                ratio = float("inf") if info.file_size else 0.0
            else:
                ratio = info.file_size / info.compress_size
            if ratio > limits.max_compression_ratio:
                raise ArchiveError(
                    f"archive entry {relative!r} compresses more than "
                    f"{limits.max_compression_ratio:g}x, which looks like an archive bomb"
                )

        entries.append((info, relative))

    missing = [name for name in required_files if name not in names]
    if missing:
        raise ArchiveError(
            "archive is missing required file(s): " + ", ".join(sorted(missing))
        )

    return entries


def _extract_entry(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    destination: Path,
    limits: ArchiveLimits,
    already_written: int,
) -> int:
    """Stream one entry, enforcing per-entry and running total byte caps."""
    written = 0
    try:
        with archive.open(info) as source, open(destination, "wb") as sink:
            while True:
                chunk = source.read(_CHUNK_SIZE)
                if not chunk:
                    break
                written += len(chunk)
                if written > limits.max_entry_bytes:
                    raise ArchiveError(
                        f"archive entry {info.filename!r} is larger than the per-file "
                        f"limit of {limits.max_entry_bytes} bytes"
                    )
                if already_written + written > limits.max_uncompressed_bytes:
                    raise ArchiveError(
                        "archive expands to more than the configured uncompressed "
                        f"size limit of {limits.max_uncompressed_bytes} bytes"
                    )
                sink.write(chunk)
    except zipfile.BadZipFile as exc:
        raise ArchiveError("archive is corrupt") from exc
    return written


def safe_extract_zip(
    zip_path: Path,
    target_dir: Path,
    *,
    limits: ArchiveLimits | None = None,
    required_files: tuple[str, ...] = (),
) -> list[Path]:
    """Validate and extract ``zip_path`` into ``target_dir``.

    Returns the extracted file paths. Raises :class:`ArchiveError` and removes
    ``target_dir`` on any failure, so a rejected upload leaves nothing behind.
    """
    limits = limits or ArchiveLimits.from_settings()
    zip_path = Path(zip_path)
    target_dir = Path(target_dir)

    if not zipfile.is_zipfile(zip_path):
        raise ArchiveError("uploaded file is not a valid zip archive")

    try:
        with zipfile.ZipFile(zip_path) as archive:
            entries = _validate_entries(archive, limits, required_files)

            target_dir.mkdir(parents=True, exist_ok=True)
            resolved_root = target_dir.resolve()
            extracted: list[Path] = []
            written_total = 0

            for info, relative in entries:
                destination = target_dir / relative
                if not str(destination.parent.resolve()).startswith(
                    str(resolved_root)
                ):
                    raise ArchiveError(
                        f"archive entry {relative!r} escapes the bundle directory"
                    )
                if info.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                    continue

                destination.parent.mkdir(parents=True, exist_ok=True)
                written_total += _extract_entry(
                    archive, info, destination, limits, written_total
                )
                extracted.append(destination)

            return extracted
    except BaseException:
        shutil.rmtree(target_dir, ignore_errors=True)
        raise


def resolve_declared_path(
    bundle_dir: Path,
    declared: str,
    *,
    label: str,
    limits: ArchiveLimits | None = None,
) -> Path:
    """Resolve a path declared inside ``model.yaml`` and keep it in the bundle."""
    limits = limits or ArchiveLimits.from_settings()
    bundle_dir = Path(bundle_dir)
    relative = _normalise_entry_path(declared, limits, label=label)
    resolved = (bundle_dir / relative).resolve()
    root = bundle_dir.resolve()
    if resolved != root and root not in resolved.parents:
        raise ArchiveError(f"{label} points outside the model bundle: {declared!r}")
    return resolved
