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


def get_logger(level: LogLevel):
    logger.add(
        sys.stdout,
        level=level.value,
        format="{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}",
    )
    return logger

