"""The catalog of databases the user has registered.

The catalog stores paths and display names only. It does not open files; the data layer
validates a file before anything is added here.
"""

import json
import logging
from dataclasses import asdict, dataclass, field

from voicedbquery.config.paths import ensure, settings_dir

log = logging.getLogger(__name__)


@dataclass
class RegisteredDatabase:
    name: str
    path: str
    synonyms: dict = field(default_factory=dict)  # spoken word -> real table or column name


class Catalog:
    def __init__(self, databases: "list[RegisteredDatabase] | None" = None):
        self.databases: list[RegisteredDatabase] = list(databases or [])

    @staticmethod
    def path():
        return settings_dir() / "catalog.json"

    @classmethod
    def load(cls) -> "Catalog":
        try:
            raw = json.loads(cls.path().read_text(encoding="utf-8"))
        except FileNotFoundError:
            return cls()
        except (OSError, ValueError) as exc:
            log.warning("Could not read catalog, starting empty: %s", exc)
            return cls()
        items = []
        for entry in raw.get("databases", []):
            try:
                items.append(RegisteredDatabase(entry["name"], entry["path"], dict(entry.get("synonyms", {}))))
            except (KeyError, TypeError):
                log.warning("Skipping malformed catalog entry: %r", entry)
        return cls(items)

    def save(self) -> None:
        ensure(settings_dir())
        payload = {"databases": [asdict(d) for d in self.databases]}
        self.path().write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def names(self) -> list:
        return [d.name for d in self.databases]

    def get(self, name: str) -> "RegisteredDatabase | None":
        wanted = name.strip().lower()
        for d in self.databases:
            if d.name.lower() == wanted:
                return d
        return None

    def find(self, words: str) -> "RegisteredDatabase | None":
        """Loose match for spoken names: 'nba' matches 'NBA five seasons'."""
        exact = self.get(words)
        if exact:
            return exact
        wanted = words.strip().lower()
        for d in self.databases:
            if wanted and wanted in d.name.lower():
                return d
        return None

    def add(self, name: str, path: str) -> RegisteredDatabase:
        name = name.strip()
        if not name:
            raise ValueError("The database needs a name.")
        if self.get(name):
            raise ValueError(f"A database called {name} is already registered.")
        entry = RegisteredDatabase(name, str(path))
        self.databases.append(entry)
        return entry

    def remove(self, name: str) -> bool:
        entry = self.get(name)
        if not entry:
            return False
        self.databases.remove(entry)
        return True
