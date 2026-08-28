#!/mastr/.venv/bin/python3

import os
import signal
import subprocess
import threading
import time

import schedule

from utils.mastr_logger import get_mastr_logger, LogLevel

logger = get_mastr_logger(LogLevel.INFO)

_is_running = False
_lock = threading.Lock()
_shutdown = False


def signal_handler(sig, frame):
    global _shutdown
    logger.info(f"Received signal {sig}, shutting down gracefully...")
    _shutdown = True


def run_mastr_download():
    """Execute the download-mastr.sh script"""
    global _is_running
    
    with _lock:
        if _is_running:
            logger.info("Skipping: previous MASTR download still in progress")
            return
        _is_running = True
    
    start_time = time.time()
    try:
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

        # Wait with timeout
        try:
            process.communicate(timeout=14400)
            duration = time.time() - start_time
            if process.returncode == 0:
                logger.info(f"MASTR download script completed successfully in {duration:.2f}s")
            else:
                logger.error(f"MASTR download script failed with return code {process.returncode} after {duration:.2f}s")
        except subprocess.TimeoutExpired:
            # Kill the entire process group (parent + all children)
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                process.wait(timeout=30)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                # Process already dead or still hanging; force kill
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                    process.wait(timeout=10)
                except ProcessLookupError:
                    pass
            logger.error("MASTR download script timed out after 4 hours")
    except Exception as e:
        logger.error(f"Error running MASTR download script: {e}")
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
        run_mastr_download()
        logger.info("Pipeline run complete, exiting (no recurring schedule)")
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
