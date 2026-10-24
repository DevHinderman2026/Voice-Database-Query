"""Deterministic sentence patterns. Produces a raw QueryIntent whose names are still spoken words.

The validator resolves the names against the live schema. Nothing here touches SQL.
"""

import re

from voicedbquery.query.intent import Aggregate, Filter, OrderBy, ParseError, QueryIntent

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "twenty five": 25,
    "thirty": 30, "forty": 40, "fifty": 50, "hundred": 100, "a hundred": 100,
}

WHERE_WORDS = r"(?:where|with|have|has|had|that have|that has|who have|who has|which have|which has|whose|having|that are|who are|which are|that is)"
VERB = r"(?:please\s+)?(?:(?:can|could|would) you\s+)?(?:show|list|get|display|find|select|give|fetch|pull|see|what are|what is|which|who are|tell)?\s*(?:me\s+)?(?:the\s+|all\s+|all the\s+|all of the\s+|every\s+|each\s+)?"
TAIL = r"(?P<tail>(?:\s+(?:" + WHERE_WORDS + r"|sorted|ordered|order|sort|ranked|rank|limit|only|just)\b.*)?)"

# Comparison operators, longest spellings first so the regex prefers them.
_OPS = [
    ("is not empty", "is not null"), ("is not missing", "is not null"), ("is not blank", "is not null"),
    ("is empty", "is null"), ("is missing", "is null"), ("is blank", "is null"), ("is null", "is null"),
    ("is not null", "is not null"),
    ("greater than or equal to", ">="), ("less than or equal to", "<="),
    ("at least", ">="), ("at most", "<="), ("or more", ">="), ("or less", "<="),
    ("greater than", ">"), ("more than", ">"), ("higher than", ">"), ("bigger than", ">"), ("over", ">"),
    ("above", ">"), ("after", ">"), ("later than", ">"), ("newer than", ">"),
    ("less than", "<"), ("fewer than", "<"), ("lower than", "<"), ("smaller than", "<"), ("under", "<"),
    ("below", "<"), ("before", "<"), ("earlier than", "<"), ("older than", "<"),
    ("is not equal to", "!="), ("not equal to", "!="), ("is not", "!="), ("isn't", "!="), ("does not equal", "!="),
    ("starts with", "starts"), ("begins with", "starts"), ("ends with", "ends"),
    ("contains", "contains"), ("containing", "contains"), ("includes", "contains"), ("including", "contains"),
    ("like", "contains"), ("has", "contains"), ("have", "contains"), ("mentions", "contains"),
    ("is equal to", "="), ("equal to", "="), ("equals", "="), ("is", "="), ("are", "="), ("was", "="),
    ("named", "="), ("called", "="), ("of", "="), ("in", "="), ("from", "="), ("for", "="), ("=", "="),
    ("==", "="), ("!=", "!="), (">=", ">="), ("<=", "<="), (">", ">"), ("<", "<"),
]
_OP_PATTERN = "|".join(re.escape(w) for w, _ in sorted(_OPS, key=lambda x: -len(x[0])))
_OP_LOOKUP = dict(_OPS)
_COND_RE = re.compile(r"^(?P<col>.+?)\s+(?P<op>" + _OP_PATTERN + r")(?:\s+(?P<val>.+))?$")

_DIR_DESC = {"descending", "desc", "highest first", "largest first", "biggest first", "high to low",
             "most first", "newest first", "latest first", "z to a", "reverse", "reversed", "backwards"}
_DIR_ASC = {"ascending", "asc", "lowest first", "smallest first", "low to high", "fewest first",
            "oldest first", "earliest first", "alphabetically", "alphabetical", "a to z"}
_HIGH = {"top", "highest", "best", "most", "biggest", "largest", "greatest", "first", "leading", "max", "maximum"}
_LOW = {"bottom", "lowest", "worst", "least", "fewest", "smallest", "last", "min", "minimum"}
_AGG = {
    "average": "AVG", "mean": "AVG", "avg": "AVG", "typical": "AVG",
    "total": "SUM", "sum": "SUM", "sum of": "SUM", "combined": "SUM", "overall": "SUM",
    "minimum": "MIN", "min": "MIN", "lowest": "MIN", "smallest": "MIN", "least": "MIN", "earliest": "MIN",
    "maximum": "MAX", "max": "MAX", "highest": "MAX", "largest": "MAX", "biggest": "MAX", "most": "MAX",
    "latest": "MAX", "greatest": "MAX",
    "count": "COUNT", "number": "COUNT", "how many": "COUNT",
}


# Spoken numbers (decision D21). Vosk writes numbers as words: "points over one thousand two hundred".
_UNIT = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9}
_TEEN = {"ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
         "seventeen": 17, "eighteen": 18, "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_SCALE = {"hundred": 100, "thousand": 1000, "million": 1000000}
_NUM_WORD = "(?:" + "|".join(sorted(list(_UNIT) + list(_TEEN) + list(_TENS) + list(_SCALE), key=len, reverse=True)) + ")"
_NUM_RUN = re.compile(r"\b(?:a\s+(?=hundred|thousand|million))?" + _NUM_WORD +
                      r"(?:(?:[\s-]+(?:and[\s-]+)?)" + _NUM_WORD + r")*\b", re.IGNORECASE)
_KEEP_ONE_AFTER = {"which", "the", "that", "this", "each", "every", "any", "no", "some", "another", "a"}


def _number_value(words: list) -> str:
    if any(w in _SCALE for w in words):
        total = current = 0
        for w in words:
            if w in _UNIT:
                current += _UNIT[w]
            elif w in _TEEN:
                current += _TEEN[w]
            elif w in _TENS:
                current += _TENS[w]
            elif w == "hundred":
                current = (current or 1) * 100
            else:
                total += (current or 1) * _SCALE[w]
                current = 0
        return str(total + current)
    groups, open_tens = [], False
    for w in words:
        if w in _UNIT and open_tens:
            groups[-1] += _UNIT[w]
            open_tens = False
        elif w in _UNIT:
            groups.append(_UNIT[w])
            open_tens = False
        elif w in _TEEN:
            groups.append(_TEEN[w])
            open_tens = False
        else:
            groups.append(_TENS[w])
            open_tens = True
    if len(groups) == 2 and 10 <= groups[0] <= 99 and 10 <= groups[1] <= 99:
        return f"{groups[0]}{groups[1]:02d}"          # a year: "twenty twenty three" is 2023
    return " ".join(str(g) for g in groups)


def spoken_numbers(text: str) -> str:
    """Turn number words into digits: "one thousand two hundred" -> "1200", "three point five" -> "3.5"."""
    def replace(m):
        words = [w for w in re.split(r"[\s-]+", m.group(0).lower()) if w and w != "and"]
        if words and words[0] == "a":
            words = words[1:]
        if words == ["one"]:
            before = text[:m.start()].split()
            if before and before[-1].lower() in _KEEP_ONE_AFTER:
                return m.group(0)                     # "which one", "the one": not a number
        return _number_value(words)

    out = _NUM_RUN.sub(replace, text)
    return re.sub(r"\b(\d+) point (\d+)\b", r"\1.\2", out, flags=re.IGNORECASE)


def normalize(text: str, lower: bool = True) -> str:
    """Tidy a question. With lower=False the same steps run but capitals are kept, so the two
    results line up character for character and typed values can get their capitals back."""
    t = text.strip()
    t = re.sub(r"[?!.]+$", "", t)
    t = re.sub(r"'s ", " ", t, flags=re.IGNORECASE)
    t = re.sub(r"\s+", " ", t)
    t = spoken_numbers(t)
    for word, n in sorted(NUMBER_WORDS.items(), key=lambda kv: -len(kv[0])):
        t = re.sub(r"\b(top|first|bottom|limit|only|just|last|highest|lowest|best|worst)\s+" + re.escape(word) + r"\b",
                   lambda m: f"{m.group(1)} {n}", t, flags=re.IGNORECASE)
    t = t.strip()
    return t.lower() if lower else t


def _restore_case(intent: QueryIntent, original: str) -> None:
    """Put the user's capitals back into text values ("Cleveland", not "cleveland")."""
    folded = original.lower()
    for f in intent.filters:
        if isinstance(f.value, str) and f.value:
            at = folded.find(f.value)
            if at >= 0:
                f.value = original[at:at + len(f.value)]


def _split_database(text: str):
    m = re.search(r"\s*(?:in|from|of|on|using)\s+(?:the\s+)?(?P<db>[\w\- ]+?)\s+(?:database|db)\b", text)
    if not m:
        return text, None
    return (text[:m.start()] + " " + text[m.end():]).strip(), m.group("db").strip()


def _value(raw: "str | None"):
    if raw is None:
        return None
    v = raw.strip().strip("'\"")
    if re.fullmatch(r"-?\d+", v):
        return int(v)
    if re.fullmatch(r"-?\d*\.\d+", v):
        return float(v)
    return v


def parse_conditions(clause: str) -> list:
    filters = []
    for part in re.split(r"\s+and\s+", clause.strip()):
        if not part:
            continue
        m = _COND_RE.match(part)
        if not m:
            raise ParseError(f"I did not understand the condition: {part}. Try a form like: points over 1000.")
        op = _OP_LOOKUP[m.group("op")]
        val = m.group("val")
        if op in ("is null", "is not null"):
            if val:
                raise ParseError(f"I did not understand: {part}.")
            filters.append(Filter(m.group("col").strip(), op))
            continue
        if val is None:
            raise ParseError(f"The condition {part} needs a value.")
        filters.append(Filter(m.group("col").strip(), op, _value(val)))
    return filters


def parse_tail(tail: str) -> dict:
    out = {"filters": [], "order_by": [], "limit": None}
    tail = tail.strip()
    m = re.search(r"\s*\b(?:limit|only|just|first|top)\s+(\d+)\s*$", tail)
    if m:
        out["limit"] = int(m.group(1))
        tail = tail[:m.start()].strip()
    m = re.search(
        r"\s*\b(?:sorted|ordered|order|sort|ranked|rank)\s+by\s+(?P<col>[\w ]+?)"
        r"(?:\s+(?P<dir>" + "|".join(re.escape(d) for d in sorted(_DIR_DESC | _DIR_ASC, key=len, reverse=True)) + r"))?\s*$",
        tail)
    if m:
        out["order_by"] = [OrderBy(m.group("col").strip(), (m.group("dir") or "") in _DIR_DESC)]
        tail = tail[:m.start()].strip()
    m = re.match(r"^" + WHERE_WORDS + r"\s+(?P<cond>.+)$", tail)
    if m:
        out["filters"] = parse_conditions(m.group("cond"))
        tail = ""
    if tail:
        raise ParseError(f"I did not understand this part: {tail}.")
    return out


def _apply_tail(intent: QueryIntent, tail: str) -> QueryIntent:
    parsed = parse_tail(tail)
    intent.filters.extend(parsed["filters"])
    if parsed["order_by"] and not intent.order_by:
        intent.order_by = parsed["order_by"]
    if parsed["limit"] is not None:
        intent.limit = parsed["limit"]
    return intent


def _cols(text: str) -> list:
    return [c.strip() for c in re.split(r",|\band\b", text) if c.strip()]


_P_COUNT = re.compile(
    r"^(?:how many|count|count the|count all|number of|the number of|what is the number of|total number of)\s+"
    r"(?P<table>[\w ]+?)(?:\s+(?:are there|is there|exist|do we have|have we got|in total|altogether))?" + TAIL + r"$")

_P_AGG_GROUPED_FIRST = re.compile(
    r"^(?:what is the |what's the |the |find the |get the |show the |show me the |give me the |tell me the )?"
    r"(?P<func>average|mean|avg|typical|total|sum|sum of|combined|minimum|min|lowest|smallest|earliest|maximum|max|highest|largest|biggest|latest)\s+"
    r"(?P<col>[\w ]+?)\s+(?:per|for each|for every|by)\s+(?P<group>[\w ]+?)\s+(?:in|of|for|from|across)\s+(?:the\s+)?(?P<table>[\w ]+?)" + TAIL + r"$")

_P_AGG = re.compile(
    r"^(?:what is the |what's the |the |find the |get the |show the |show me the |give me the |tell me the )?"
    r"(?P<func>average|mean|avg|typical|total|sum|sum of|combined|minimum|min|lowest|smallest|earliest|maximum|max|highest|largest|biggest|latest)\s+"
    r"(?P<col>[\w ]+?)\s+(?:in|of|for|from|across)\s+(?:the\s+)?(?P<table>[\w ]+?)"
    r"(?P<group>\s+(?:per|for each|for every|grouped by|group by|by)\s+[\w ]+?)?" + TAIL + r"$")

_P_TOP = re.compile(
    r"^" + VERB + r"(?P<dir>top|first|highest|best|most|bottom|lowest|worst|least|fewest|last)\s+(?P<n>\d+)?\s*"
    r"(?P<table>[\w ]+?)\s+(?:by|in|on|ranked by|sorted by|ordered by|with the most|with the highest|with the best|"
    r"with the lowest|with the fewest|with the least|with the worst|with most|with highest|with lowest)\s+(?P<col>[\w ]+?)" + TAIL + r"$")

_P_SUPERLATIVE = re.compile(
    r"^(?:which|what|who)?\s*(?:is the |are the )?(?P<table>[\w ]+?)\s+(?:has|have|had|got|with|scored|holds|hold)\s+the\s+"
    r"(?P<dir>most|highest|best|biggest|largest|fewest|lowest|least|worst|smallest)\s+(?P<col>[\w ]+?)" + TAIL + r"$")

_P_DISTINCT = re.compile(
    r"^" + VERB + r"(?:different|distinct|unique|list of)\s+(?P<col>[\w ]+?)\s+(?:in|of|from|for)\s+(?:the\s+)?(?P<table>[\w ]+?)" + TAIL + r"$")

_P_COLUMNS = re.compile(
    r"^" + VERB + r"(?P<cols>[\w ,]+?)\s+(?:from|in|of|for)\s+(?:the\s+|all\s+|every\s+)?(?P<table>[\w ]+?)" + TAIL + r"$")

_P_TABLE = re.compile(r"^" + VERB + r"(?P<table>[\w ]+?)" + TAIL + r"$")


def spoken_database(question: str) -> "str | None":
    """The database named in a question ("... in the movies database"), or None."""
    return _split_database(normalize(question))[1]


def parse(question: str) -> QueryIntent:
    """Parse a question into a raw QueryIntent. Raises ParseError with advice if it cannot."""
    text = normalize(question)
    if not text:
        raise ParseError("Say or type a question first.")
    text, database = _split_database(text)
    intent = _parse_body(text)
    intent.database = database
    _restore_case(intent, normalize(question, lower=False))
    return intent


def _parse_body(text: str) -> QueryIntent:
    m = _P_COUNT.match(text)
    if m:
        intent = QueryIntent(table=m.group("table").strip(), aggregate=Aggregate("COUNT", None))
        return _apply_tail(intent, m.group("tail"))

    m = _P_AGG_GROUPED_FIRST.match(text)
    if m:
        intent = QueryIntent(table=m.group("table").strip(),
                             aggregate=Aggregate(_AGG[m.group("func")], m.group("col").strip()),
                             group_by=[m.group("group").strip()])
        return _apply_tail(intent, m.group("tail"))

    m = _P_AGG.match(text)
    if m:
        intent = QueryIntent(table=m.group("table").strip(),
                             aggregate=Aggregate(_AGG[m.group("func")], m.group("col").strip()))
        if m.group("group"):
            intent.group_by = [re.sub(r"^\s*(?:per|for each|for every|grouped by|group by|by)\s+", "", m.group("group")).strip()]
        return _apply_tail(intent, m.group("tail"))

    m = _P_TOP.match(text)
    if m:
        descending = m.group("dir") in _HIGH
        intent = QueryIntent(table=m.group("table").strip(),
                             order_by=[OrderBy(m.group("col").strip(), descending)],
                             limit=int(m.group("n")) if m.group("n") else 10)
        return _apply_tail(intent, m.group("tail"))

    m = _P_SUPERLATIVE.match(text)
    if m:
        descending = m.group("dir") in _HIGH
        intent = QueryIntent(table=m.group("table").strip(),
                             order_by=[OrderBy(m.group("col").strip(), descending)], limit=1)
        return _apply_tail(intent, m.group("tail"))

    m = _P_DISTINCT.match(text)
    if m:
        intent = QueryIntent(table=m.group("table").strip(), columns=[m.group("col").strip()], distinct=True)
        return _apply_tail(intent, m.group("tail"))

    m = _P_COLUMNS.match(text)
    if m:
        intent = QueryIntent(table=m.group("table").strip(), columns=_cols(m.group("cols")))
        return _apply_tail(intent, m.group("tail"))

    m = _P_TABLE.match(text)
    if m:
        intent = QueryIntent(table=m.group("table").strip())
        return _apply_tail(intent, m.group("tail"))

    raise ParseError("I did not understand that question. Try forms like: show all teams; "
                     "top 5 players by points; how many movies where year is 1994; average points per team in player stats.")
