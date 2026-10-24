"""The engine: opens a database, answers questions, runs typed SQL. Thin layers above call this."""

import logging
import threading
from dataclasses import dataclass

from voicedbquery.config.catalog import Catalog
from voicedbquery.config.history import History
from voicedbquery.config.settings import Settings
from voicedbquery.data.connection import open_readonly, validate_database_file
from voicedbquery.data.executor import QueryResult, run_query
from voicedbquery.data.schema import Schema, introspect
from voicedbquery.query import grammar, sql_builder, typed_sql, validator
from voicedbquery.query.intent import ParseError, QueryIntent, describe
from voicedbquery.query.synonyms import SynonymMap

log = logging.getLogger(__name__)


@dataclass
class Outcome:
    question: str
    description: str
    sql: str
    params: list
    result: QueryResult
    intent: "QueryIntent | None" = None


class Engine:
    def __init__(self, settings: Settings, catalog: Catalog, history: "History | None" = None):
        self.settings = settings
        self.catalog = catalog
        self.history = history
        self.current_name: "str | None" = None
        self.schema: "Schema | None" = None
        self.synonyms = SynonymMap()
        self._conn = None
        self._lock = threading.Lock()
        self.cancel_event = threading.Event()

    # Databases

    def open(self, name: str) -> Schema:
        entry = self.catalog.get(name)
        if entry is None:
            raise ParseError(f"No database called {name} is registered.")
        return self.open_path(entry.path, entry.name, entry.synonyms)

    def open_path(self, path, name: "str | None" = None, synonyms: "dict | None" = None) -> Schema:
        self.close()
        conn = open_readonly(path)
        self.schema = introspect(conn)
        self._conn = conn
        self.current_name = name or validate_database_file(path).stem
        self.synonyms = SynonymMap(synonyms)
        log.info("Opened %s with tables %s", self.current_name, self.schema.table_names)
        return self.schema

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
        self._conn = None
        self.schema = None
        self.current_name = None

    def database_named_in(self, question: str) -> "str | None":
        """The registered database a question names ("top 5 movies in the movies database"), or None."""
        spoken = grammar.spoken_database(question)
        if not spoken:
            return None
        entry = self.catalog.find(spoken)
        return entry.name if entry else None

    @property
    def is_open(self) -> bool:
        return self._conn is not None

    # Questions

    def interpret(self, question: str) -> "tuple[QueryIntent, str, list]":
        if self.schema is None:
            raise ParseError("Open a database first.")
        raw = grammar.parse(question)
        intent = validator.validate(raw, self.schema, self.synonyms)
        sql, params = sql_builder.build(intent)
        return intent, sql, params

    def ask(self, question: str) -> Outcome:
        intent, sql, params = self.interpret(question)
        result = self._execute(sql, params)
        outcome = Outcome(question, describe(intent), sql, params, result, intent)
        self._record(question, sql)
        return outcome

    def run_sql(self, sql: str) -> Outcome:
        if not self.settings.typed_sql_enabled:
            raise ParseError("SQL mode is turned off in settings.")
        body = typed_sql.check_select(sql)
        result = self._execute(body, [])
        outcome = Outcome(sql, "Typed SQL statement.", body, [], result)
        self._record(sql, body)
        return outcome

    def cancel(self) -> None:
        self.cancel_event.set()
        if self._conn is not None:
            try:
                self._conn.interrupt()
            except Exception:
                pass

    def _execute(self, sql: str, params) -> QueryResult:
        if self._conn is None:
            raise ParseError("Open a database first.")
        with self._lock:
            self.cancel_event.clear()
            log.info("SQL: %s params=%r", sql, params)
            return run_query(self._conn, sql, params, row_cap=self.settings.row_cap,
                             time_limit=self.settings.time_limit_seconds, cancel_event=self.cancel_event)

    def _record(self, question: str, sql: str) -> None:
        if self.history is not None:
            self.history.add(self.current_name or "", question, sql)
            self.history.save()


def row_sentence(result: QueryResult, index: int) -> str:
    """Row 3 of 12: full_name LeBron James, pts 1126."""
    row = result.rows[index]
    cells = ", ".join(f"{col} {'empty' if val is None else val}" for col, val in zip(result.columns, row))
    return f"Row {index + 1} of {result.row_count}: {cells}."


def summary_sentence(result: QueryResult) -> str:
    if result.row_count == 0:
        return "No rows matched."
    more = f" Showing the first {result.row_cap}; there are more." if result.truncated else ""
    first = row_sentence(result, 0)
    word = "row" if result.row_count == 1 else "rows"
    return f"{result.row_count} {word} in {result.elapsed:.2f} seconds.{more} {first}"
