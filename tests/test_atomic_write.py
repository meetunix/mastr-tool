"""Tests for the atomic write helpers used by all pipeline exports.

Readers (mastr-static / mastr-app) must never see partially written files:
every export is written to a hidden temp file next to the target and moved
into place with an atomic rename.
"""

from pathlib import Path

import pytest

from utils.atomic_write import TEMP_MARKER, atomic_write, cleanup_stale_temp_files, temp_path_for


class TestAtomicWrite:
    def test_writes_content_and_leaves_no_temp(self, tmp_path):
        target = tmp_path / "wind_deutschland.csv"

        atomic_write(target, lambda temp: temp.write_text("a,b\n1,2\n", encoding="utf-8"))

        assert target.read_text(encoding="utf-8") == "a,b\n1,2\n"
        assert list(tmp_path.iterdir()) == [target]

    def test_replaces_existing_target(self, tmp_path):
        target = tmp_path / "wind_deutschland.csv"
        target.write_text("old content", encoding="utf-8")

        atomic_write(target, lambda temp: temp.write_text("new content", encoding="utf-8"))

        assert target.read_text(encoding="utf-8") == "new content"

    def test_failed_write_keeps_old_target_and_removes_temp(self, tmp_path):
        target = tmp_path / "wind_deutschland.csv"
        target.write_text("old content", encoding="utf-8")

        def failing_writer(temp: Path) -> None:
            temp.write_text("partial data", encoding="utf-8")
            raise RuntimeError("export aborted")

        with pytest.raises(RuntimeError):
            atomic_write(target, failing_writer)

        assert target.read_text(encoding="utf-8") == "old content"
        assert list(tmp_path.iterdir()) == [target]

    def test_temp_path_is_hidden_and_next_to_target(self, tmp_path):
        target = tmp_path / "stromspeicher_deutschland.csv"
        temp = temp_path_for(target)

        assert temp.parent == target.parent
        assert temp.name.startswith(".")
        assert TEMP_MARKER in temp.name
        assert temp.name.endswith(target.name) is False  # carries the target name plus markers

    def test_temp_paths_are_unique(self, tmp_path):
        target = tmp_path / "kernkraft_bayern.csv"
        temps = {temp_path_for(target) for _ in range(50)}
        assert len(temps) == 50


class TestCleanupStaleTempFiles:
    def test_removes_only_stale_temp_files(self, tmp_path):
        stale_csv = tmp_path / ".wind_deutschland.csv.tmp-123-abcdef12"
        stale_dump = tmp_path / ".mastr-latest.sql.tmp-999-deadbeef"
        stale_csv.write_text("partial", encoding="utf-8")
        stale_dump.write_bytes(b"\x00partial")

        regular = tmp_path / "wind_deutschland.csv"
        regular.write_text("complete", encoding="utf-8")
        hidden_no_marker = tmp_path / ".hidden-config"
        hidden_no_marker.write_text("keep me", encoding="utf-8")

        removed = cleanup_stale_temp_files(tmp_path)

        assert removed == 2
        assert not stale_csv.exists()
        assert not stale_dump.exists()
        assert regular.read_text(encoding="utf-8") == "complete"
        assert hidden_no_marker.read_text(encoding="utf-8") == "keep me"

    def test_missing_directory_is_no_error(self, tmp_path):
        assert cleanup_stale_temp_files(tmp_path / "does-not-exist") == 0

    def test_empty_directory(self, tmp_path):
        assert cleanup_stale_temp_files(tmp_path) == 0
