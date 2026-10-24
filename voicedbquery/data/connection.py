"""Open SQLite files read-only, with every write path closed.

Four independent guards make the application read-only:
1. The file is opened through a URI with mode=ro, so the operating-system handle cannot write.
2. PRAGMA query_only = ON refuses any statement that would change data.
3. An authorizer callback permits only SELECT, READ, FUNCTION, RECURSIVE, and a short list of
   read-only PRAGMAs. Everything else, including ATTACH, is denied.
4. The query grammar can only ever produce a SELECT (see voicedbquery.query).

Extension loading is never enabled. Autocommit mode means Python never issues a BEGIN.
"""

import sqlite3
from pathlib import Path
from urllib.parse import quote

SQLITE_HEADER = b"SQLite format 3\x00"
ALLOWED_EXTENSIONS = {".db", ".sqlite", ".sqlite3"}

# PRAGMAs that only read schema or metadata. Anything not listed is denied.
READ_ONLY_PRAGMAS = {
    "table_info", "table_xinfo", "table_list", "index_list", "index_info", "index_xinfo",
    "foreign_key_list", "database_list", "collation_list", "function_list",
    "user_version", "schema_version", "page_size", "page_count", "encoding",
}

_ALLOWED_ACTIONS = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    getattr(sqlite3, "SQLITE_RECURSIVE", 33),
}


class DatabaseFileError(ValueError):
    """The chosen file is not a usable SQLite database."""


def validate_database_file(path) -> Path:
    """Return the canonical path if the file exists, has a database extension, and has the SQLite header."""
    p = Path(path).expanduser()
    try:
        p = p.resolve(strict=True)
    except (OSError, RuntimeError):
        raise DatabaseFileError(f"There is no file at {path}.")
    if not p.is_file():
        raise DatabaseFileError(f"{p.name} is not a file.")
    if p.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise DatabaseFileError(f"{p.name} does not end in .db, .sqlite, or .sqlite3.")
    try:
        with p.open("rb") as fh:
            header = fh.read(len(SQLITE_HEADER))
    except OSError as exc:
        raise DatabaseFileError(f"{p.name} could not be read: {exc.strerror or exc}.")
    if header != SQLITE_HEADER:
        raise DatabaseFileError(f"{p.name} is not a SQLite database.")
    return p


def _authorizer(action, arg1, arg2, db_name, trigger):
    if action in _ALLOWED_ACTIONS:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_PRAGMA and arg1 and arg1.lower() in READ_ONLY_PRAGMAS:
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def read_only_uri(path: Path) -> str:
    posix = path.as_posix()
    if not posix.startswith("/"):
        posix = "/" + posix  # Windows drive paths become file:///C:/...
    return "file://" + quote(posix) + "?mode=ro"


def open_readonly(path) -> sqlite3.Connection:
    """Open a validated database file with all four read-only guards in place."""
    p = validate_database_file(path)
    conn = sqlite3.connect(
        read_only_uri(p),
        uri=True,
        check_same_thread=False,   # queries run in a worker thread; the engine serializes access
        isolation_level=None,      # autocommit: never issue BEGIN
    )
    conn.execute("PRAGMA query_only = ON")
    conn.set_authorizer(_authorizer)
    return conn
