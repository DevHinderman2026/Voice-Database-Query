"""Query history: the question and the SQL it became. Never the results."""

import json
import logging
from datetime import datetime

from voicedbquery.config.paths import ensure, settings_dir

log = logging.getLogger(__name__)
MAX_ENTRIES = 500


class History:
    def __init__(self):
        self.entries: list[dict] = []

    @staticmethod
    def path():
        return settings_dir() / "history.json"

    @classmethod
    def load(cls) -> "History":
        h = cls()
        try:
            h.entries = list(json.loads(cls.path().read_text(encoding="utf-8")))
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as exc:
            log.warning("Could not read history: %s", exc)
        return h

    def add(self, database: str, question: str, sql: str) -> None:
        self.entries.append({
            "when": datetime.now().isoformat(timespec="seconds"),
            "database": database,
            "question": question,
            "sql": sql,
        })
        self.entries = self.entries[-MAX_ENTRIES:]

    def save(self) -> None:
        try:
            ensure(settings_dir())
            self.path().write_text(json.dumps(self.entries, indent=2), encoding="utf-8")
        except OSError as exc:
            log.warning("Could not save history: %s", exc)
