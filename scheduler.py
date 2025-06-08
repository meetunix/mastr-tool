#!/mastr/.venv/bin/python3

import schedule
import time
import subprocess

from utils.mastr_logger import get_mastr_logger, LogLevel

logger = get_mastr_logger(LogLevel.INFO)


def run_mastr_download():
    """Execute the download-mastr.sh script"""
    try:
        logger.info("Starting MASTR download script")

        script_path = "/mastr/download-mastr.sh"

        result = subprocess.run(["/bin/bash", script_path], cwd="/mastr", capture_output=False, text=True, timeout=3600)

        if result.returncode == 0:
            logger.info("MASTR download script completed successfully")
            if result.stdout:
                logger.info(f"Output: {result.stdout}")
        else:
            logger.error(f"MASTR download script failed with return code {result.returncode}")
            if result.stderr:
                logger.error(f"Error: {result.stderr}")

    except subprocess.TimeoutExpired:
        logger.error("MASTR download script timed out after 1 hour")
    except Exception as e:
        logger.error(f"Error running MASTR download script: {e}")


def main():
    logger.info("Starting MASTR scheduler")

    schedule.every(30).minutes.do(run_mastr_download)

    logger.info("Running initial MASTR import")
    run_mastr_download()

    logger.info("Scheduler started - running every 30 minutes")
    while True:
        schedule.run_pending()
        time.sleep(300)  # Check every 5 minutes


if __name__ == "__main__":
    main()
