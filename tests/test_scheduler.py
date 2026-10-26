"""Tests for the scheduler: pipeline result propagation and the one-shot
behavior when MASTR_FORCE_USING_EXISTING_DUMP is set.

The download script is replaced by a fake process - no pipeline, no network.
"""

import subprocess

import pytest

import scheduler
from scheduler import _force_using_existing_dump, main, run_mastr_download


class FakeProcess:
    def __init__(self, returncode=0, timeout=False):
        self.returncode = None
        self._returncode = returncode
        self._timeout = timeout
        self.pid = 12345

    def communicate(self, timeout=None):
        if self._timeout:
            raise subprocess.TimeoutExpired(cmd="download-mastr.sh", timeout=timeout)
        self.returncode = self._returncode
        return ("", "")

    def wait(self, timeout=None):
        return self._returncode


def patch_process(monkeypatch, **kwargs):
    monkeypatch.setattr(scheduler.subprocess, "Popen", lambda *args, **kw: FakeProcess(**kwargs))


class TestRunMastrDownload:
    def test_success_returns_true(self, monkeypatch):
        patch_process(monkeypatch, returncode=0)
        assert run_mastr_download() is True

    def test_failure_returns_false(self, monkeypatch):
        patch_process(monkeypatch, returncode=1)
        assert run_mastr_download() is False

    def test_timeout_returns_false_and_kills_process_group(self, monkeypatch):
        patch_process(monkeypatch, timeout=True)
        killed = []
        monkeypatch.setattr(scheduler.os, "getpgid", lambda pid: 4242)
        monkeypatch.setattr(scheduler.os, "killpg", lambda pgid, sig: killed.append((pgid, sig)))
        assert run_mastr_download() is False
        assert (4242, scheduler.signal.SIGTERM) in killed

    def test_spawn_error_returns_false(self, monkeypatch):
        def broken_popen(*args, **kwargs):
            raise OSError("no such file")

        monkeypatch.setattr(scheduler.subprocess, "Popen", broken_popen)
        assert run_mastr_download() is False


class TestForceModeExitCode:
    def test_successful_run_exits_cleanly(self, monkeypatch):
        monkeypatch.setenv("MASTR_FORCE_USING_EXISTING_DUMP", "true")
        monkeypatch.setattr(scheduler, "run_mastr_download", lambda: True)
        assert main() is None  # returns without SystemExit

    def test_failed_run_exits_non_zero(self, monkeypatch):
        monkeypatch.setenv("MASTR_FORCE_USING_EXISTING_DUMP", "true")
        monkeypatch.setattr(scheduler, "run_mastr_download", lambda: False)
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 1


class TestForceFlagParsing:
    @pytest.mark.parametrize("value", ["true", "TRUE", "yes", "Yes"])
    def test_enabled_values(self, monkeypatch, value):
        monkeypatch.setenv("MASTR_FORCE_USING_EXISTING_DUMP", value)
        assert _force_using_existing_dump() is True

    @pytest.mark.parametrize("value", ["false", "", "no", "1"])
    def test_disabled_values(self, monkeypatch, value):
        monkeypatch.setenv("MASTR_FORCE_USING_EXISTING_DUMP", value)
        assert _force_using_existing_dump() is False

    def test_unset(self, monkeypatch):
        monkeypatch.delenv("MASTR_FORCE_USING_EXISTING_DUMP", raising=False)
        assert _force_using_existing_dump() is False
