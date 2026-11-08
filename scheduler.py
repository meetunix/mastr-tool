#!/mastr/.venv/bin/python3

import os
import signal
import subprocess
import sys
import threading
import time

import schedule

from utils.mastr_logger import get_mastr_logger, LogLevel

logger = get_mastr_logger(LogLevel.INFO)

_is_running = False
_lock = threading.Lock()
_shutdown = False

PIPELINE_TIMEOUT_S = 14400
# docker stop waits 10 s and Kubernetes 30 s before killing the container
SHUTDOWN_GRACE_PERIOD_S = 5


def signal_handler(sig, frame):
    global _shutdown
    logger.info(f"Received signal {sig}, shutting down gracefully...")
    _shutdown = True


def _terminate_process_group(process: subprocess.Popen, grace_period: float) -> None:
    """Terminate the script and all its children (the whole process group)."""
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        process.wait(timeout=grace_period)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        # Process already dead or still hanging; force kill
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            process.wait(timeout=10)
        except ProcessLookupError:
            pass


def run_mastr_download() -> bool:
    """Execute the download-mastr.sh script. Returns True on success."""
    global _is_running

    with _lock:
        if _is_running:
            logger.info("Skipping: previous MASTR download still in progress")
            return True
        _is_running = True

    start_time = time.time()
    try:
        if _shutdown:
            return False

        logger.info("Starting MASTR download script")

        script_path = "/mastr/download-mastr.sh"

        # Create process in a new process group to kill all children on timeout
        process = subprocess.Popen(
            ["/bin/bash", script_path],
            cwd="/mastr",
            stdout=None,
            stderr=None,
            text=True,
            preexec_fn=os.setsid  # Unix: create new process group
        )

        # The script runs in its own session and does not receive the
        # container's SIGTERM: wait in short steps and forward a shutdown
        while True:
            try:
                process.wait(timeout=1)
                break
            except subprocess.TimeoutExpired:
                if _shutdown:
                    logger.info("Terminating MASTR download script due to shutdown")
                    _terminate_process_group(process, SHUTDOWN_GRACE_PERIOD_S)
                    return False
                if time.time() - start_time >= PIPELINE_TIMEOUT_S:
                    _terminate_process_group(process, 30)
                    logger.error("MASTR download script timed out after 4 hours")
                    return False

        duration = time.time() - start_time
        if process.returncode == 0:
            logger.info(f"MASTR download script completed successfully in {duration:.2f}s")
            return True
        logger.error(f"MASTR download script failed with return code {process.returncode} after {duration:.2f}s")
        return False
    except Exception as e:
        logger.error(f"Error running MASTR download script: {e}")
        return False
    finally:
        _is_running = False


def _force_using_existing_dump():
    """Return True if MASTR_FORCE_USING_EXISTING_DUMP is enabled."""
    return os.environ.get("MASTR_FORCE_USING_EXISTING_DUMP", "").lower() in ("yes", "true")


def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info("Starting MASTR scheduler")

    if _force_using_existing_dump():
        logger.info("MASTR_FORCE_USING_EXISTING_DUMP is set, running pipeline once without scheduling")
        success = run_mastr_download()
        if not success:
            # exit non-zero so the restart policy retries the run
            logger.error("Pipeline run failed")
            sys.exit(1)
        # stay idle instead of exiting: restart policies like
        # "unless-stopped" (compose) or a Deployment would otherwise start
        # the whole pipeline over and over again
        logger.info("Pipeline run complete, waiting idle until shutdown (no recurring schedule)")
        while not _shutdown:
            time.sleep(1)
        logger.info("Scheduler shutdown complete")
        return

    schedule.every(30).minutes.do(run_mastr_download)

    logger.info("Running initial MASTR import")
    run_mastr_download()

    logger.info("Scheduler started - running every 30 minutes")
    while not _shutdown:
        schedule.run_pending()
        time.sleep(1)

    logger.info("Scheduler shutdown complete")


if __name__ == "__main__":
    main()
