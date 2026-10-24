"""Build exactly one SELECT with bound parameters from a validated QueryIntent.

Identifiers are double-quoted schema names. Values are never placed in the SQL text.
Single-table queries use bare column names; joined queries qualify every column with its table.
"""

from voicedbquery.data.schema import quote_identifier as q
from voicedbquery.query.intent import AGGREGATE_SORT, ColumnRef, QueryIntent

_AGG_ALIAS = {"COUNT": "count", "SUM": "total", "AVG": "average", "MIN": "lowest", "MAX": "highest"}


def aggregate_alias(intent: QueryIntent) -> "str | None":
    if not intent.aggregate:
        return None
    a = intent.aggregate
    base = _AGG_ALIAS[a.func]
    if a.func == "COUNT":
        return base
    return f"{base}_{a.column}"


def build(intent: QueryIntent) -> "tuple[str, list]":
    params: list = []
    joined = bool(intent.joins)

    def col(ref) -> str:
        if isinstance(ref, ColumnRef):
            return f"{q(ref.table)}.{q(ref.column)}" if joined else q(ref.column)
        return q(str(ref))

    if intent.aggregate:
        a = intent.aggregate
        if a.column is None:
            target = "*"
        else:
            target = ("DISTINCT " if a.distinct else "") + col(a.column)
        expr = f"{a.func}({target})"
        if a.func == "AVG":
            expr = f"ROUND({expr}, 2)"
        select_items = [f"{col(g)} AS {q(str(g))}" if joined else col(g) for g in intent.group_by]
        select_items.append(f"{expr} AS {q(aggregate_alias(intent))}")
        select = ", ".join(select_items)
    elif intent.columns:
        names = [str(c) for c in intent.columns]
        items = []
        for c in intent.columns:
            if joined:
                alias = str(c) if names.count(str(c)) == 1 else f"{c.table}_{c.column}"
                items.append(f"{col(c)} AS {q(alias)}")
            else:
                items.append(col(c))
        select = ("DISTINCT " if intent.distinct else "") + ", ".join(items)
    else:
        select = f"{q(intent.table)}.*" if joined else "*"

    sql = f"SELECT {select} FROM {q(intent.table)}"
    for join in intent.joins:
        conditions = " AND ".join(f"{col(left)} = {col(right)}" for left, right in join.on)
        sql += f" JOIN {q(join.table)} ON {conditions}"

    if intent.filters:
        clauses = []
        for f in intent.filters:
            c = col(f.column)
            if f.op == "is null":
                clauses.append(f"{c} IS NULL")
            elif f.op == "is not null":
                clauses.append(f"{c} IS NOT NULL")
            elif f.op == "contains":
                clauses.append(f"{c} LIKE ?")
                params.append(f"%{f.value}%")
            elif f.op == "starts":
                clauses.append(f"{c} LIKE ?")
                params.append(f"{f.value}%")
            elif f.op == "ends":
                clauses.append(f"{c} LIKE ?")
                params.append(f"%{f.value}")
            elif f.op in ("=", "!=") and isinstance(f.value, str):
                clauses.append(f"{c} {f.op} ? COLLATE NOCASE")
                params.append(f.value)
            else:
                clauses.append(f"{c} {f.op} ?")
                params.append(f.value)
        sql += " WHERE " + " AND ".join(clauses)

    if intent.group_by:
        sql += " GROUP BY " + ", ".join(col(g) for g in intent.group_by)

    if intent.order_by:
        parts = []
        for o in intent.order_by:
            target = q(aggregate_alias(intent)) if o.column == AGGREGATE_SORT else col(o.column)
            parts.append(f"{target} {'DESC' if o.descending else 'ASC'}")
        sql += " ORDER BY " + ", ".join(parts)
    elif intent.aggregate and intent.group_by:
        sql += f" ORDER BY {q(aggregate_alias(intent))} DESC"

    if intent.limit is not None:
        sql += " LIMIT ?"
        params.append(int(intent.limit))

    return sql, params
