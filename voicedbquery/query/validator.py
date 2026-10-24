"""Resolve every spoken name in a QueryIntent against the live schema.

After this step every table and column is the schema's own spelling, wrapped in a ColumnRef,
and every filter value is typed to match its column. Unknown names are rejected with suggestions.

Two-table questions: when a column is not in the question's main table, the resolver looks in
tables linked to it by foreign keys, up to two steps away (two steps covers a junction table,
such as movies to roles to people). The links it walks become JOINs.
"""

from voicedbquery.data.schema import Schema, Table
from voicedbquery.query.intent import (AGGREGATE_SORT, Aggregate, ColumnRef, Filter, Join, OrderBy,
                                       ParseError, QueryIntent)
from voicedbquery.query.synonyms import SynonymMap

MAX_HOPS = 2
AGGREGATE_WORDS = {"count", "total", "average", "result", "number", "sum", "mean"}


def _resolve_table(name: str, schema: Schema, syn: SynonymMap) -> Table:
    real = syn.resolve(name, schema.table_names)
    if real is None:
        hints = syn.suggest(name, schema.table_names)
        advice = f" Did you mean {', '.join(hints)}?" if hints else f" The tables are: {', '.join(schema.table_names)}."
        raise ParseError(f"There is no table called {name}.{advice}")
    return schema.table(real)


class _Resolver:
    """Resolves column phrases for one question and remembers which linked tables were used."""

    def __init__(self, schema: Schema, base: Table, syn: SynonymMap):
        self.schema = schema
        self.base = base
        self.syn = syn
        self.paths = schema.paths_from(base.name, MAX_HOPS)
        self.used = []          # lower-case table names other than base, in first-use order

    def _reachable(self):
        """Linked tables, nearest first, then alphabetical."""
        others = [k for k in self.paths if k != self.base.name.lower()]
        return sorted(others, key=lambda k: (len(self.paths[k]), k))

    def _use(self, table: Table) -> None:
        key = table.name.lower()
        if key != self.base.name.lower() and key not in self.used:
            self.used.append(key)

    def column(self, phrase: str) -> ColumnRef:
        # 1. "team name", "player name": a table word followed by a column phrase.
        words = phrase.split()
        for cut in range(len(words) - 1, 0, -1):
            table_word, rest = " ".join(words[:cut]), " ".join(words[cut:])
            table_name = self.syn.resolve(table_word, self.schema.table_names)
            if table_name and table_name.lower() in self.paths:
                table = self.schema.table(table_name)
                real = self.syn.resolve(rest, table.column_names)
                if real:
                    self._use(table)
                    return ColumnRef(table.name, real)

        # 2. The main table.
        real = self.syn.resolve(phrase, self.base.column_names)
        if real:
            return ColumnRef(self.base.name, real)

        # 3. Linked tables, nearest first. Two equally near matches are ambiguous.
        found = []
        for key in self._reachable():
            table = self.schema.table(key)
            real = self.syn.resolve(phrase, table.column_names)
            if real:
                if found and len(self.paths[key]) > len(self.paths[found[0][0].name.lower()]):
                    break
                found.append((table, real))
        if len(found) == 1:
            table, real = found[0]
            self._use(table)
            return ColumnRef(table.name, real)
        if len(found) > 1:
            options = " or ".join(f"{_singular(t.name)} {phrase}" for t, _r in found)
            raise ParseError(f"{phrase} is in more than one linked table. Say {options}.")

        hints = self.syn.suggest(phrase, self.base.column_names)
        advice = f" Did you mean {', '.join(hints)}?" if hints else \
            f" The columns in {self.base.name} are: {', '.join(self.base.column_names)}."
        raise ParseError(f"There is no column called {phrase} in {self.base.name} or the tables linked to it.{advice}")

    def joins(self) -> list:
        """JOINs for every linked table used, in walking order, each table once."""
        joins, joined = [], {self.base.name.lower()}
        for key in self.used:
            for link in self.paths[key]:
                target = link.to_table.lower()
                if target in joined:
                    continue
                on = tuple((ColumnRef(link.from_table, a), ColumnRef(link.to_table, b)) for a, b in link.pairs)
                joins.append(Join(link.to_table, on))
                joined.add(target)
        return joins

    def default_columns(self, mentioned: list) -> list:
        """Columns to show when the question joined tables but did not name columns:
        the main table's name column, any key column of a joined table that is not used to link
        tables (such as season; never a bare ID), then every column the question mentioned."""
        cols = []
        label = self.base.label_column
        if label:
            cols.append(ColumnRef(self.base.name, label))
        else:
            cols.extend(ColumnRef(self.base.name, c) for c in self.base.primary_key)
        joins = self.joins()
        link_columns = {ref for join in joins for pair in join.on for ref in pair}
        for join in joins:
            table = self.schema.table(join.table)
            for pk in table.primary_key:
                ref = ColumnRef(table.name, pk)
                if ref not in link_columns and not self.schema.is_foreign_key_column(table.name, pk):
                    cols.append(ref)
        for ref in mentioned:
            if isinstance(ref, ColumnRef):
                cols.append(ref)
        seen, unique = set(), []
        for ref in cols:
            if ref not in seen:
                seen.add(ref)
                unique.append(ref)
        return unique


def _singular(name: str) -> str:
    return name[:-1] if name.endswith("s") and not name.endswith("ss") else name


def _type_value(value, ref: ColumnRef, schema: Schema):
    col = schema.table(ref.table).column(ref.column)
    if col is None or value is None:
        return value
    if col.is_numeric and isinstance(value, str):
        text = value.replace(",", "").strip()
        try:
            return int(text)
        except ValueError:
            try:
                return float(text)
            except ValueError:
                return value
    if not col.is_numeric and isinstance(value, (int, float)):
        return str(value)
    return value


def validate(intent: QueryIntent, schema: Schema, syn: SynonymMap) -> QueryIntent:
    base = _resolve_table(intent.table, schema, syn)
    res = _Resolver(schema, base, syn)
    resolved = QueryIntent(table=base.name, distinct=intent.distinct, limit=intent.limit, database=intent.database)

    resolved.columns = [res.column(c) for c in intent.columns]
    resolved.group_by = [res.column(g) for g in intent.group_by]

    if intent.aggregate:
        col = None if intent.aggregate.column is None else res.column(intent.aggregate.column)
        resolved.aggregate = Aggregate(intent.aggregate.func, col)

    for f in intent.filters:
        ref = res.column(f.column)
        resolved.filters.append(Filter(ref, f.op, _type_value(f.value, ref, schema)))

    for o in intent.order_by:
        if resolved.aggregate and str(o.column).lower() in AGGREGATE_WORDS:
            resolved.order_by.append(OrderBy(AGGREGATE_SORT, o.descending))
        else:
            resolved.order_by.append(OrderBy(res.column(o.column), o.descending))

    resolved.joins = res.joins()
    if resolved.joins:
        a = resolved.aggregate
        if a and a.func == "COUNT" and a.column is None and len(base.primary_key) == 1:
            # "how many players scored over 2000": count each player once, not each joined row
            resolved.aggregate = Aggregate("COUNT", ColumnRef(base.name, base.primary_key[0]), distinct=True)
        if not resolved.columns and not resolved.aggregate:
            mentioned = [o.column for o in resolved.order_by] + [f.column for f in resolved.filters]
            resolved.columns = res.default_columns(mentioned)
            resolved.distinct = True

    if resolved.limit is not None and resolved.limit <= 0:
        raise ParseError("The number of rows must be at least 1.")
    return resolved
