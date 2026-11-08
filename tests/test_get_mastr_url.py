"""Tests for the ETag check of get_mastr_url.py. No network: the remote ETag
is passed in directly."""

from get_mastr_url import get_local_etag, is_etag_new


class TestIsEtagNew:
    def test_changed_etag_is_new(self, tmp_path):
        etag_file = tmp_path / "etag.txt"
        etag_file.write_text('"old"')
        assert is_etag_new(etag_file, '"new"') is True

    def test_same_etag_is_not_new(self, tmp_path):
        etag_file = tmp_path / "etag.txt"
        etag_file.write_text('"same"')
        assert is_etag_new(etag_file, '"same"') is False

    def test_check_does_not_store_the_etag(self, tmp_path):
        """Regression: the ETag used to be stored by the check itself, so a
        pipeline run failing afterwards was never retried."""
        etag_file = tmp_path / "etag.txt"
        etag_file.write_text('"old"')
        assert is_etag_new(etag_file, '"new"') is True
        assert is_etag_new(etag_file, '"new"') is True
        assert etag_file.read_text() == '"old"'

    def test_missing_local_etag_is_new(self, tmp_path):
        """No successful pipeline run recorded yet: the run must happen."""
        etag_file = tmp_path / "etag.txt"
        assert is_etag_new(etag_file, '"new"') is True
        assert not etag_file.exists()

    def test_unknown_remote_etag_is_not_new(self, tmp_path):
        etag_file = tmp_path / "etag.txt"
        etag_file.write_text('"old"')
        assert is_etag_new(etag_file, None) is False

    def test_trailing_newline_of_the_shell_is_ignored(self, tmp_path):
        """download-mastr.sh writes the file with printf '%s\\n'."""
        etag_file = tmp_path / "etag.txt"
        etag_file.write_text('"same"\n')
        assert get_local_etag(etag_file) == '"same"'
        assert is_etag_new(etag_file, '"same"') is False
