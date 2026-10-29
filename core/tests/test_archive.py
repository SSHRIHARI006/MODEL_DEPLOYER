"""SEC-04: safe archive extraction."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from core.archive import (
    ArchiveError,
    ArchiveLimits,
    _extract_entry,
    resolve_declared_path,
    safe_extract_zip,
)

MANIFEST = (
    "name: test_model\n"
    "framework: sklearn\n"
    "python_version: '3.12'\n"
    "requirements: requirements.txt\n"
    "model_artifact: model.pkl\n"
)


def _write_zip(path: Path, files: dict[str, bytes | str]) -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return path


def _limits(**overrides) -> ArchiveLimits:
    base = dict(
        max_uncompressed_bytes=1024,
        max_entry_bytes=512,
        max_entries=16,
        max_path_length=120,
        max_compression_ratio=None,
    )
    base.update(overrides)
    return ArchiveLimits(**base)


def _valid_files() -> dict[str, str]:
    return {"model.yaml": MANIFEST, "requirements.txt": "scikit-learn==1.8.0\n", "model.pkl": "x"}


class TestValidArchives:
    def test_extracts_a_normal_bundle(self, tmp_path):
        zip_path = _write_zip(tmp_path / "bundle.zip", _valid_files())
        target = tmp_path / "out"

        extracted = safe_extract_zip(
            zip_path, target, limits=_limits(), required_files=("model.yaml",)
        )

        assert (target / "model.yaml").exists()
        assert {path.name for path in extracted} == {
            "model.yaml",
            "requirements.txt",
            "model.pkl",
        }

    def test_extracts_nested_directories(self, tmp_path):
        zip_path = _write_zip(
            tmp_path / "bundle.zip",
            {"model.yaml": MANIFEST, "artifacts/nested/model.pkl": "x"},
        )
        target = tmp_path / "out"

        safe_extract_zip(zip_path, target, limits=_limits())

        assert (target / "artifacts" / "nested" / "model.pkl").read_text() == "x"

    def test_accepts_entries_without_archiver_attributes(self, tmp_path):
        zip_path = tmp_path / "bundle.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            info = zipfile.ZipInfo("model.yaml")
            info.external_attr = 0
            archive.writestr(info, MANIFEST)

        safe_extract_zip(zip_path, tmp_path / "out", limits=_limits())

        assert (tmp_path / "out" / "model.yaml").exists()


class TestUnsafePathsAreRejected:
    @pytest.mark.parametrize(
        "name",
        [
            "../escaped.txt",
            "nested/../../escaped.txt",
            "/etc/passwd",
            "\\windows\\absolute.txt",
            "C:/windows/absolute.txt",
            "..\\escaped.txt",
        ],
    )
    def test_rejects_unsafe_entry_names(self, tmp_path, name):
        zip_path = _write_zip(tmp_path / "bundle.zip", {"model.yaml": MANIFEST, name: "boom"})
        target = tmp_path / "out"

        with pytest.raises(ArchiveError):
            safe_extract_zip(zip_path, target, limits=_limits())

        assert not target.exists(), "a rejected upload must leave nothing behind"
        assert not (tmp_path / "escaped.txt").exists()

    def test_rejects_symlink_entries(self, tmp_path):
        zip_path = tmp_path / "bundle.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr("model.yaml", MANIFEST)
            link = zipfile.ZipInfo("model.pkl")
            link.external_attr = (0o120777 << 16)  # S_IFLNK
            archive.writestr(link, "/etc/passwd")

        with pytest.raises(ArchiveError, match="not a regular file"):
            safe_extract_zip(zip_path, tmp_path / "out", limits=_limits())

    def test_rejects_overlong_entry_paths(self, tmp_path):
        long_name = "a" * 200 + ".txt"
        zip_path = _write_zip(tmp_path / "bundle.zip", {"model.yaml": MANIFEST, long_name: "x"})

        with pytest.raises(ArchiveError, match="longer than"):
            safe_extract_zip(zip_path, tmp_path / "out", limits=_limits(max_path_length=50))


class TestSizeLimitsAreRejected:
    def test_rejects_too_many_entries(self, tmp_path):
        files = {"model.yaml": MANIFEST}
        files.update({f"file-{index}.txt": "x" for index in range(20)})
        zip_path = _write_zip(tmp_path / "bundle.zip", files)

        with pytest.raises(ArchiveError, match="more than the limit"):
            safe_extract_zip(zip_path, tmp_path / "out", limits=_limits(max_entries=5))

    def test_rejects_declared_uncompressed_total(self, tmp_path):
        zip_path = _write_zip(
            tmp_path / "bundle.zip",
            {"model.yaml": MANIFEST, "one.bin": "0" * 600, "two.bin": "0" * 600},
        )

        with pytest.raises(ArchiveError, match="uncompressed size limit"):
            safe_extract_zip(
                zip_path,
                tmp_path / "out",
                limits=_limits(max_uncompressed_bytes=1000, max_entry_bytes=4096),
            )

    def test_rejects_oversized_single_entry(self, tmp_path):
        zip_path = _write_zip(
            tmp_path / "bundle.zip", {"model.yaml": MANIFEST, "big.bin": "0" * 4000}
        )

        with pytest.raises(ArchiveError, match="per-file limit"):
            safe_extract_zip(zip_path, tmp_path / "out", limits=_limits(max_entry_bytes=100))

    def test_rejects_high_compression_ratio(self, tmp_path):
        zip_path = _write_zip(
            tmp_path / "bundle.zip", {"model.yaml": MANIFEST, "bomb.bin": "0" * 200_000}
        )

        with pytest.raises(ArchiveError, match="archive bomb"):
            safe_extract_zip(
                zip_path,
                tmp_path / "out",
                limits=_limits(
                    max_uncompressed_bytes=10_000_000,
                    max_entry_bytes=10_000_000,
                    max_compression_ratio=10,
                ),
            )

    def test_ratio_check_can_be_disabled(self, tmp_path):
        zip_path = _write_zip(
            tmp_path / "bundle.zip", {"model.yaml": MANIFEST, "bomb.bin": "0" * 200_000}
        )

        safe_extract_zip(
            zip_path,
            tmp_path / "out",
            limits=_limits(
                max_uncompressed_bytes=10_000_000,
                max_entry_bytes=10_000_000,
                max_compression_ratio=None,
            ),
        )

        assert (tmp_path / "out" / "bomb.bin").exists()

    # The byte caps are enforced while writing, not only from ZIP metadata: a
    # header can understate how much data an entry will produce. Exercised
    # directly on the streaming helper because metadata validation runs first.
    def test_running_per_entry_cap_stops_an_understated_entry(self, tmp_path):
        zip_path = _write_zip(
            tmp_path / "bundle.zip", {"model.yaml": MANIFEST, "big.bin": "0" * 5000}
        )
        limits = _limits(max_uncompressed_bytes=1_000_000, max_entry_bytes=100)

        with zipfile.ZipFile(zip_path) as archive:
            info = archive.infolist()[-1]
            with pytest.raises(ArchiveError, match="per-file limit"):
                _extract_entry(
                    archive, info, tmp_path / "out.bin", limits, already_written=0
                )

    def test_running_total_cap_stops_an_understated_entry(self, tmp_path):
        zip_path = _write_zip(
            tmp_path / "bundle.zip", {"model.yaml": MANIFEST, "big.bin": "0" * 5000}
        )
        limits = _limits(max_uncompressed_bytes=1000, max_entry_bytes=1_000_000)

        with zipfile.ZipFile(zip_path) as archive:
            info = archive.infolist()[-1]
            with pytest.raises(ArchiveError, match="uncompressed size limit"):
                _extract_entry(
                    archive, info, tmp_path / "out.bin", limits, already_written=999_500
                )


class TestMalformedArchives:
    def test_rejects_a_non_zip_payload(self, tmp_path):
        path = tmp_path / "bundle.zip"
        path.write_bytes(b"not a zip at all")

        with pytest.raises(ArchiveError, match="not a valid zip"):
            safe_extract_zip(path, tmp_path / "out", limits=_limits())

    def test_rejects_missing_required_file(self, tmp_path):
        zip_path = _write_zip(tmp_path / "bundle.zip", {"requirements.txt": "x"})

        with pytest.raises(ArchiveError, match="model.yaml"):
            safe_extract_zip(
                zip_path, tmp_path / "out", limits=_limits(), required_files=("model.yaml",)
            )

        assert not (tmp_path / "out").exists()


class TestResolveDeclaredPath:
    def test_resolves_inside_the_bundle(self, tmp_path):
        bundle = tmp_path / "bundle"
        (bundle / "nested").mkdir(parents=True)
        (bundle / "nested" / "model.pkl").write_text("x")

        resolved = resolve_declared_path(bundle, "nested/model.pkl", label="model_artifact")

        assert resolved == (bundle / "nested" / "model.pkl").resolve()

    @pytest.mark.parametrize(
        "declared", ["../outside.txt", "/etc/passwd", "nested/../../outside.txt", ""]
    )
    def test_rejects_paths_outside_the_bundle(self, tmp_path, declared):
        bundle = tmp_path / "bundle"
        bundle.mkdir()
        (tmp_path / "outside.txt").write_text("secret")

        with pytest.raises(ArchiveError):
            resolve_declared_path(bundle, declared, label="requirements")
