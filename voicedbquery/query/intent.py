"""The structured meaning of a question, before and after validation.

Before validation every name is the user's spoken word (a plain string). After validation every
column is a ColumnRef holding the schema's own table and column spelling.
"""

from dataclasses import dataclass, field

OPERATORS = {"=", "!=", ">", ">=", "<", "<=", "contains", "starts", "ends", "is null", "is not null"}
AGGREGATES = {"COUNT", "SUM", "AVG", "MIN", "MAX"}
AGGREGATE_SORT = "__aggregate__"   # OrderBy column meaning "the aggregate result"


class ParseError(ValueError):
    """The question could not be understood. The message says what to try."""


@dataclass(frozen=True)
class ColumnRef:
    table: str
    column: str

    def __str__(self) -> str:
        return self.column


@dataclass
class Join:
    table: str
    on: tuple   # ((ColumnRef left, ColumnRef right), ...)


@dataclass
class Filter:
    column: object          # str before validation, ColumnRef after
    op: str
    value: object = None


@dataclass
class Aggregate:
    func: str               # one of AGGREGATES
    column: object          # None means COUNT(*); str before validation, ColumnRef after
    distinct: bool = False  # COUNT(DISTINCT ...) so a join does not count one row many times


@dataclass
class OrderBy:
    column: object
    descending: bool = False


@dataclass
class QueryIntent:
    table: str
    columns: list = field(default_factory=list)      # empty means every column
    filters: list = field(default_factory=list)
    aggregate: "Aggregate | None" = None
    group_by: list = field(default_factory=list)
    order_by: list = field(default_factory=list)
    limit: "int | None" = None
    distinct: bool = False
    database: "str | None" = None                     # spoken database name, if any
    joins: list = field(default_factory=list)         # filled in by the validator only


_OP_WORDS = {
    "=": "is", "!=": "is not", ">": "is over", ">=": "is at least", "<": "is under",
    "<=": "is at most", "contains": "contains", "starts": "starts with", "ends": "ends with",
    "is null": "is empty", "is not null": "is not empty",
}


def describe(intent: QueryIntent) -> str:
    """Read the intent back in plain English, for the Understood-as area."""
    if intent.aggregate:
        a = intent.aggregate
        if a.func == "COUNT":
            head = f"number of {intent.table}"
        else:
            what = {"SUM": "total", "AVG": "average", "MIN": "lowest", "MAX": "highest"}[a.func]
            head = f"{what} {a.column} in {intent.table}"
        if intent.group_by:
            head += " for each " + ", ".join(str(g) for g in intent.group_by)
    elif intent.columns:
        head = ("distinct " if intent.distinct and not intent.joins else "") + \
            ", ".join(str(c) for c in intent.columns) + f" from {intent.table}"
    else:
        head = f"all columns from {intent.table}"
    parts = [head]
    if intent.filters:
        conds = []
        for f in intent.filters:
            if f.op in ("is null", "is not null"):
                conds.append(f"{f.column} {_OP_WORDS[f.op]}")
            else:
                conds.append(f"{f.column} {_OP_WORDS[f.op]} {f.value}")
        parts.append("where " + " and ".join(conds))
    if intent.order_by:
        parts.append("sorted by " + ", ".join(
            f"{'the result' if o.column == AGGREGATE_SORT else o.column} "
            f"{'highest first' if o.descending else 'lowest first'}" for o in intent.order_by))
    if intent.limit is not None:
        parts.append(f"first {intent.limit}")
    if intent.joins:
        parts.append("linked with " + " and ".join(j.table for j in intent.joins))
    text = ", ".join(parts)
    if intent.database:
        text += f", in the {intent.database} database"
    return text[0].upper() + text[1:] + "."
