import enum
import sys
from multiprocessing.util import get_logger

from loguru import logger

logger.remove()


class LogLevel(enum.Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


def get_mastr_logger(level: LogLevel):
    logger.add(
        sys.stdout,
        level=level.value,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {file} | {level} | {message}",
    )
    return logger

