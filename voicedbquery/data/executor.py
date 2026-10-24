"""Run one SELECT with a time limit, a row cap, and a cancel switch."""

import sqlite3
import threading
import time
from dataclasses import dataclass, field


class QueryError(Exception):
    """A plain-English problem with running the query."""


class QueryTimeout(QueryError):
    pass


class QueryCancelled(QueryError):
    pass


class ReadOnlyViolation(QueryError):
    """Something tried to write. The guards stopped it."""


@dataclass
class QueryResult:
    columns: list
    rows: list
    truncated: bool
    elapsed: float
    row_cap: int = 500
    notes: list = field(default_factory=list)

    @property
    def row_count(self) -> int:
        return len(self.rows)


def run_query(conn: sqlite3.Connection, sql: str, params=(), row_cap: int = 500,
              time_limit: float = 5.0, cancel_event: "threading.Event | None" = None) -> QueryResult:
    deadline = time.monotonic() + time_limit

    def progress():
        if cancel_event is not None and cancel_event.is_set():
            return 1
        if time.monotonic() > deadline:
            return 1
        return 0

    conn.set_progress_handler(progress, 1000)
    started = time.monotonic()
    try:
        cursor = conn.execute(sql, tuple(params))
        columns = [d[0] for d in cursor.description] if cursor.description else []
        rows = cursor.fetchmany(row_cap + 1)
        truncated = len(rows) > row_cap
        rows = rows[:row_cap]
    except sqlite3.OperationalError as exc:
        text = str(exc)
        if "interrupted" in text:
            if cancel_event is not None and cancel_event.is_set():
                raise QueryCancelled("The query was cancelled.")
            raise QueryTimeout(f"The query took longer than {time_limit:g} seconds and was stopped.")
        if "readonly" in text or "query_only" in text:
            raise ReadOnlyViolation("That would change the database, which this application never does.")
        raise QueryError(f"SQLite reported: {text}.")
    except sqlite3.DatabaseError as exc:
        text = str(exc)
        if "not authorized" in text:
            raise ReadOnlyViolation("That statement is not allowed. Only reading data is permitted.")
        raise QueryError(f"SQLite reported: {text}.")
    finally:
        conn.set_progress_handler(None, 0)
    return QueryResult(columns, rows, truncated, time.monotonic() - started, row_cap)
