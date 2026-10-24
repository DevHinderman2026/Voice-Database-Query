"""User settings, stored as JSON in the settings folder."""

import json
import logging
from dataclasses import asdict, dataclass, fields

from voicedbquery.config.paths import ensure, settings_dir

log = logging.getLogger(__name__)


@dataclass
class Settings:
    run_immediately: bool = True          # decision O1: run on Enter, no read-back step
    typed_sql_enabled: bool = True        # decision O2: SQL mode available
    speech_output: bool = True            # announce through a screen reader when one is running
    speech_without_screen_reader: bool = False  # decision O6 default: no SAPI voice unless asked
    listening_beeps: bool = True           # decision D20: beeps instead of saying "Listening"
    listen_seconds: int = 12               # longest one spoken question can take (decision D17)
    row_cap: int = 500
    time_limit_seconds: float = 5.0
    last_database: str = ""

    @classmethod
    def path(cls):
        return settings_dir() / "settings.json"

    @classmethod
    def load(cls) -> "Settings":
        try:
            raw = json.loads(cls.path().read_text(encoding="utf-8"))
        except FileNotFoundError:
            return cls()
        except (OSError, ValueError) as exc:
            log.warning("Could not read settings, using defaults: %s", exc)
            return cls()
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in raw.items() if k in known})

    def save(self) -> None:
        ensure(settings_dir())
        self.path().write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
