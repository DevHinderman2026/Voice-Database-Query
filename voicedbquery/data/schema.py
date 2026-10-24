"""Schema introspection: tables, columns, types, keys, and the links between tables."""

import sqlite3
from collections import deque
from dataclasses import dataclass, field

NUMERIC_TYPES = ("INT", "REAL", "NUM", "DOUB", "FLOA", "DEC")

# Column names that usually hold the human-readable name of a row, best first.
LABEL_NAMES = ("full_name", "name", "title", "display_name", "nickname", "abbreviation", "label")


def quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


@dataclass(frozen=True)
class Column:
    name: str
    type: str
    primary_key: bool
    not_null: bool

    @property
    def is_numeric(self) -> bool:
        t = self.type.upper()
        return any(marker in t for marker in NUMERIC_TYPES)


@dataclass(frozen=True)
class Table:
    name: str
    columns: tuple

    @property
    def column_names(self) -> list:
        return [c.name for c in self.columns]

    @property
    def primary_key(self) -> list:
        return [c.name for c in self.columns if c.primary_key]

    def column(self, name: str) -> "Column | None":
        wanted = name.lower()
        for c in self.columns:
            if c.name.lower() == wanted:
                return c
        return None

    @property
    def label_column(self) -> "str | None":
        """The column a person would call this row's name, if there is one."""
        by_lower = {c.name.lower(): c.name for c in self.columns}
        for candidate in LABEL_NAMES:
            if candidate in by_lower:
                return by_lower[candidate]
        return None


@dataclass(frozen=True)
class ForeignKey:
    """from_table.from_columns refers to to_table.to_columns."""
    from_table: str
    from_columns: tuple
    to_table: str
    to_columns: tuple


@dataclass(frozen=True)
class Link:
    """One step of a join path, written in the direction it is walked."""
    from_table: str
    to_table: str
    pairs: tuple  # ((from_column, to_column), ...)


@dataclass
class Schema:
    tables: dict                              # lower-case name -> Table
    foreign_keys: list = field(default_factory=list)

    @property
    def table_names(self) -> list:
        return [t.name for t in self.tables.values()]

    def table(self, name: str) -> "Table | None":
        return self.tables.get(name.lower())

    def links_from(self, table_name: str) -> list:
        """Every Link that starts at this table, following foreign keys in either direction."""
        name = table_name.lower()
        out = []
        for fk in self.foreign_keys:
            if fk.from_table.lower() == name:
                out.append(Link(fk.from_table, fk.to_table, tuple(zip(fk.from_columns, fk.to_columns))))
            if fk.to_table.lower() == name:
                out.append(Link(fk.to_table, fk.from_table, tuple(zip(fk.to_columns, fk.from_columns))))
        return out

    def paths_from(self, start: str, max_hops: int = 2) -> dict:
        """Shortest join path from start to every table within max_hops. Maps lower-case name -> [Link, ...]."""
        start_key = start.lower()
        paths = {start_key: []}
        queue = deque([start_key])
        while queue:
            current = queue.popleft()
            if len(paths[current]) >= max_hops:
                continue
            for link in sorted(self.links_from(current), key=lambda l: l.to_table.lower()):
                key = link.to_table.lower()
                if key not in paths and key in self.tables:
                    paths[key] = paths[current] + [link]
                    queue.append(key)
        return paths

    def is_foreign_key_column(self, table_name: str, column: str) -> bool:
        for fk in self.foreign_keys:
            if fk.from_table.lower() == table_name.lower() and column in fk.from_columns:
                return True
        return False

    def describe(self) -> str:
        """Plain-English summary for the status area and the screen reader."""
        return "; ".join(f"{t.name}: {', '.join(t.column_names)}" for t in self.tables.values())


def introspect(conn: sqlite3.Connection) -> Schema:
    names = [
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view') "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    tables = {}
    for name in names:
        cols = []
        for _cid, col_name, col_type, notnull, _default, pk in conn.execute(
            f"PRAGMA table_info({quote_identifier(name)})"
        ):
            cols.append(Column(col_name, col_type or "", bool(pk), bool(notnull)))
        tables[name.lower()] = Table(name, tuple(cols))

    foreign_keys = []
    for name in names:
        grouped = {}
        for fk_id, _seq, target, from_col, to_col, *_rest in conn.execute(
            f"PRAGMA foreign_key_list({quote_identifier(name)})"
        ):
            grouped.setdefault((fk_id, target), []).append((from_col, to_col))
        for (_fk_id, target), pairs in grouped.items():
            target_table = tables.get(target.lower())
            if target_table is None:
                continue
            to_cols = [t for _f, t in pairs]
            if any(t is None for t in to_cols):          # REFERENCES table with no column: its primary key
                to_cols = target_table.primary_key
            if len(to_cols) != len(pairs):
                continue
            foreign_keys.append(ForeignKey(tables[name.lower()].name, tuple(f for f, _t in pairs),
                                           target_table.name, tuple(to_cols)))
    return Schema(tables, foreign_keys)
