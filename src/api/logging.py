"""
Structured logging for the Contract Intake API.

Provides consistent, readable log output with timestamps.
"""

import logging
import sys
from datetime import datetime
from typing import Any


class StructuredFormatter(logging.Formatter):
    """Custom formatter with readable timestamps and structured output."""

    def format(self, record: logging.LogRecord) -> str:
        # ISO timestamp with milliseconds
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

        # Level padding for alignment
        level = record.levelname.ljust(8)

        # Module name (shortened)
        module = record.name.split(".")[-1] if record.name else "root"

        # Base message
        base = f"{timestamp} | {level} | {module} | {record.getMessage()}"

        # Add extra fields if present
        extras = getattr(record, "extras", None)
        if extras:
            extra_str = " | ".join(f"{k}={v}" for k, v in extras.items())
            base = f"{base} | {extra_str}"

        return base


def get_logger(name: str) -> logging.Logger:
    """Get a configured logger instance."""
    logger = logging.getLogger(name)

    # Only configure if not already configured
    if not logger.handlers:
        logger.setLevel(logging.INFO)

        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StructuredFormatter())
        logger.addHandler(handler)

        # Prevent propagation to root logger
        logger.propagate = False

    return logger


def log_request(
    logger: logging.Logger,
    action: str,
    **kwargs: Any,
) -> None:
    """Log a request with structured extras."""
    record = logger.makeRecord(
        logger.name,
        logging.INFO,
        "",
        0,
        action,
        (),
        None,
    )
    record.extras = kwargs
    logger.handle(record)


def log_error(
    logger: logging.Logger,
    action: str,
    error: Exception,
    **kwargs: Any,
) -> None:
    """Log an error with structured extras."""
    record = logger.makeRecord(
        logger.name,
        logging.ERROR,
        "",
        0,
        f"{action}: {type(error).__name__}: {error}",
        (),
        None,
    )
    record.extras = kwargs
    logger.handle(record)
