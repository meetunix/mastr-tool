#!/mastr/.venv/bin/python3

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
    result = None
    try:
        logger.info("Starting MASTR download script")

        script_path = "/mastr/download-mastr.sh"

        # do not capture output - the executed scripts are logging
        result = subprocess.run(["/bin/bash", script_path], cwd="/mastr", capture_output=False, text=True, timeout=7200)
        duration = time.time() - start_time


        if result.returncode == 0:
            logger.info(f"MASTR download script completed successfully in {duration:.2f}s")
        else:
            logger.error(f"MASTR download script failed with return code {result.returncode} after {duration:.2f}s")

    except subprocess.TimeoutExpired:
        logger.error("MASTR download script timed out after 2 hours")
    except Exception as e:
        logger.error(f"Error running MASTR download script: {e}")
    finally:
        _is_running = False


def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("Starting MASTR scheduler")

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
