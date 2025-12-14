from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


class ResilientTimedRotatingFileHandler(TimedRotatingFileHandler):
    """
    TimedRotatingFileHandler that recreates the target file if it was removed
    (e.g. when the host cleans up bind-mounted logs while the container keeps running).
    """

    def emit(self, record):
        if self.stream and not Path(self.baseFilename).exists():
            try:
                self.stream.close()
            except Exception:
                pass
            self.stream = self._open()
        super().emit(record)


def configure_metrics_logger(path: str, *, when: str = "midnight", backups: int = 30, logger_name: str = "metrics.actions") -> logging.Logger:
    """
    Configure dedicated logger for action metrics.
    Writes JSON lines to the specified path with daily rotation by default.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if logger.handlers:
        same_path = all(
            getattr(handler, "baseFilename", None) == str(target)
            for handler in logger.handlers
        )
        if same_path:
            return logger
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
            handler.close()

    handler = ResilientTimedRotatingFileHandler(
        filename=target,
        when=when,
        backupCount=backups,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    return logger
