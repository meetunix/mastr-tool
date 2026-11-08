"""Tests for the scheduler: pipeline result propagation, shutdown handling
and the one-shot behavior when MASTR_FORCE_USING_EXISTING_DUMP is set.

The download script is replaced by a fake process - no pipeline, no network.
"""

import subprocess

import pytest

import scheduler
from scheduler import _force_using_existing_dump, main, run_mastr_download


class FakeProcess:
    """Runs for `running_steps` wait() calls (each one a 1 s wait step of the
    scheduler), then exits with `returncode`. Never exits if running_steps
    is None, until it is terminated by a signal."""

    instances = []

    def __init__(self, returncode=0, running_steps=0):
        self.returncode = None
        self._returncode = returncode
        self._running_steps = running_steps
        self.pid = 12345
        self.terminated = False
        FakeProcess.instances.append(self)

    def wait(self, timeout=None):
        if self.terminated:
            self.returncode = -scheduler.signal.SIGTERM
            return self.returncode
        if self._running_steps is None or self._running_steps > 0:
            if self._running_steps:
                self._running_steps -= 1
            raise subprocess.TimeoutExpired(cmd="download-mastr.sh", timeout=timeout)
        self.returncode = self._returncode
        return self._returncode


def patch_process(monkeypatch, **kwargs):
    monkeypatch.setattr(scheduler.subprocess, "Popen", lambda *args, **kw: FakeProcess(**kwargs))


@pytest.fixture(autouse=True)
def reset_shutdown(monkeypatch):
    monkeypatch.setattr(scheduler, "_shutdown", False)


@pytest.fixture
def killed(monkeypatch):
    """Records the signals sent to the process group; a signal ends the fake process."""
    signals = []

    def killpg(pgid, sig):
        signals.append((pgid, sig))
        for process in FakeProcess.instances:
            process.terminated = True

    monkeypatch.setattr(scheduler.os, "getpgid", lambda pid: 4242)
    monkeypatch.setattr(scheduler.os, "killpg", killpg)
    return signals


class TestRunMastrDownload:
    def test_success_returns_true(self, monkeypatch):
        patch_process(monkeypatch, returncode=0)
        assert run_mastr_download() is True

    def test_failure_returns_false(self, monkeypatch):
        patch_process(monkeypatch, returncode=1)
        assert run_mastr_download() is False

    def test_long_run_is_awaited(self, monkeypatch):
        patch_process(monkeypatch, returncode=0, running_steps=3)
        assert run_mastr_download() is True

    def test_timeout_returns_false_and_kills_process_group(self, monkeypatch, killed):
        patch_process(monkeypatch, running_steps=None)
        monkeypatch.setattr(scheduler, "PIPELINE_TIMEOUT_S", 0)
        assert run_mastr_download() is False
        assert killed == [(4242, scheduler.signal.SIGTERM)]

    def test_shutdown_terminates_process_group(self, monkeypatch, killed):
        """The script runs in its own session and never sees the container's
        SIGTERM - the scheduler must forward it to the process group."""
        process = FakeProcess(running_steps=None)
        monkeypatch.setattr(scheduler.subprocess, "Popen", lambda *args, **kw: process)
        fake_wait = process.wait

        def wait(timeout=None):
            # the container's SIGTERM arrives while the script is running
            scheduler.signal_handler(scheduler.signal.SIGTERM, None)
            return fake_wait(timeout)

        process.wait = wait
        assert run_mastr_download() is False
        assert killed == [(4242, scheduler.signal.SIGTERM)]

    def test_hanging_script_is_killed(self, monkeypatch):
        patch_process(monkeypatch, running_steps=None)
        monkeypatch.setattr(scheduler, "PIPELINE_TIMEOUT_S", 0)
        signals = []

        def killpg(pgid, sig):
            # the script ignores SIGTERM and only ends on SIGKILL
            signals.append(sig)
            if sig == scheduler.signal.SIGKILL:
                for process in FakeProcess.instances:
                    process.terminated = True

        monkeypatch.setattr(scheduler.os, "getpgid", lambda pid: 4242)
        monkeypatch.setattr(scheduler.os, "killpg", killpg)
        assert run_mastr_download() is False
        assert signals == [scheduler.signal.SIGTERM, scheduler.signal.SIGKILL]

    def test_no_run_after_shutdown(self, monkeypatch):
        monkeypatch.setattr(scheduler, "_shutdown", True)

        def popen(*args, **kwargs):
            raise AssertionError("no script must be started after a shutdown request")

        monkeypatch.setattr(scheduler.subprocess, "Popen", popen)
        assert run_mastr_download() is False

    def test_spawn_error_returns_false(self, monkeypatch):
        def broken_popen(*args, **kwargs):
            raise OSError("no such file")

        monkeypatch.setattr(scheduler.subprocess, "Popen", broken_popen)
        assert run_mastr_download() is False


class TestForceModeExitCode:
    def test_successful_run_stays_idle_until_shutdown(self, monkeypatch):
        """A successful one-shot run must not exit: restart policies like
        "unless-stopped" or a Deployment would rerun the whole pipeline."""
        monkeypatch.setenv("MASTR_FORCE_USING_EXISTING_DUMP", "true")
        monkeypatch.setattr(scheduler, "run_mastr_download", lambda: True)
        idle_steps = []

        def sleep(seconds):
            idle_steps.append(seconds)
            if len(idle_steps) == 3:
                scheduler.signal_handler(scheduler.signal.SIGTERM, None)

        monkeypatch.setattr(scheduler.time, "sleep", sleep)
        assert main() is None  # returns without SystemExit after the shutdown
        assert len(idle_steps) == 3

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
