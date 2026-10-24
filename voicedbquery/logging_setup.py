"""File logging. Tracebacks go here, never to the user interface."""

import logging
from logging.handlers import RotatingFileHandler

from voicedbquery.config.paths import ensure, logs_dir


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    root = logging.getLogger("voicedbquery")
    if root.handlers:
        return root
    root.setLevel(level)
    try:
        log_file = ensure(logs_dir()) / "voicedbquery.log"
        handler = RotatingFileHandler(log_file, maxBytes=512_000, backupCount=3, encoding="utf-8")
    except OSError:
        handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)
    return root
