"""The assistant: the conversational side of the program (decisions D19 and D21).

Before a spoken sentence reaches the data grammar, `detect` decides whether it is about the program
itself: help, greetings, "explain", "what databases are there", "describe the players table",
"switch to movies", "read row 3", "tell me more", "what about teams", "goodbye" and so on.
It returns a Command, or None for a data question.

Three layers, tried in order:
1. Exact phrases (the strict patterns), after polite openings such as "can you" are removed.
2. Short and social phrases: one-word requests ("explain", "tables", "columns"), greetings, thanks,
   yes and no, follow-ups.
3. Keywords, using the live table and database names, so loose wording still works
   ("give me a rundown of this database", "what's the structure of players").
   This layer stays out of the way of data questions: if a table is mentioned and no explaining
   word is used, the sentence goes to the data grammar.

Everything is deterministic (decision D5). Nothing here reaches SQL. The text functions below are
pure, so they are tested without a window.
"""

import re
from dataclasses import dataclass

from voicedbquery.data.schema import Schema, Table

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "first": 1, "second": 2, "third": 3,
    "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
}

# Command kinds. The window knows what to do for each.
HELP = "help"
EXAMPLES = "examples"
LIST_DATABASES = "list_databases"
CURRENT_DATABASE = "current_database"
DESCRIBE_DATABASE = "describe_database"   # argument: database name, or None for the current one
LIST_TABLES = "list_tables"
DESCRIBE_TABLE = "describe_table"         # argument: spoken table (or database) name
COLUMNS = "columns"                       # columns of the table being talked about
SWITCH_DATABASE = "switch_database"       # argument: spoken database name
ADD_DATABASE = "add_database"
FOLLOW_UP = "follow_up"                   # "what about teams": argument is the spoken name
MORE = "more"                             # "tell me more", "go on"
REPEAT = "repeat"
READ_RESULTS = "read_results"
READ_ROW = "read_row"                     # argument: row number, 1-based; -1 means the last row
NEXT_ROW = "next_row"
PREVIOUS_ROW = "previous_row"
READ_ALL = "read_all"
ROW_COUNT = "row_count"
LAST_QUESTION = "last_question"
CANCEL = "cancel"                         # stop talking; nothing else
GREETING = "greeting"
THANKS = "thanks"
ABOUT = "about"
HOW_ARE_YOU = "how_are_you"
YES = "yes"
NO = "no"
CONFIRM_EXIT = "confirm_exit"             # "goodbye", "quit": asks before closing
EXIT = "exit"                             # "exit the program": closes


@dataclass
class Command:
    kind: str
    argument: object = None


# What the Understood-as box shows for each command.
_LABELS = {
    HELP: "A request for help.",
    EXAMPLES: "A request for example questions.",
    LIST_DATABASES: "List the databases.",
    CURRENT_DATABASE: "Which database is open.",
    LIST_TABLES: "List the tables in the current database.",
    COLUMNS: "List the columns of the table we are talking about.",
    ADD_DATABASE: "Add a database.",
    MORE: "Tell me more.",
    REPEAT: "Repeat the last thing said.",
    READ_RESULTS: "Read the results.",
    NEXT_ROW: "Read the next result row.",
    PREVIOUS_ROW: "Read the previous result row.",
    READ_ALL: "Read all the results.",
    ROW_COUNT: "How many result rows there are.",
    LAST_QUESTION: "What my last question was.",
    CANCEL: "Stop talking.",
    GREETING: "A greeting.",
    THANKS: "Thanks.",
    ABOUT: "What this program is.",
    HOW_ARE_YOU: "Asking how the program is.",
    YES: "Yes.",
    NO: "No.",
    CONFIRM_EXIT: "Close the program (asks first).",
    EXIT: "Close the program.",
}


def describe_command(command: Command) -> str:
    """Plain words for the Understood-as box."""
    kind, arg = command.kind, command.argument
    if kind == DESCRIBE_DATABASE:
        return f"Explain the {arg} database." if arg else "Explain the current database."
    if kind == DESCRIBE_TABLE:
        return f"Describe the {arg} table."
    if kind == SWITCH_DATABASE:
        return f"Switch to the {arg} database."
    if kind == FOLLOW_UP:
        return f"What about {arg}."
    if kind == READ_ROW:
        return "Read the last result row." if arg == -1 else f"Read result row {arg}."
    return _LABELS.get(kind, "A request to the program.")


def _clean(text: str) -> str:
    t = text.strip().lower()
    t = t.replace("’", "'")
    t = re.sub(r"[?!.,;:\"]+", " ", t)
    for short, full in (("what's", "what is"), ("whats", "what is"), ("i'm", "i am"), ("it's", "it is"),
                        ("that's", "that is"), ("there's", "there is"), ("who's", "who is"), ("don't", "do not"),
                        ("i'd", "i would"), ("let's", "let us"), ("how's", "how is"), ("you're", "you are")):
        t = re.sub(r"\b" + re.escape(short) + r"\b", full, t)
    t = re.sub(r"\b(please|hey there|um+|uh+|er+|hmm+|like|just|actually|basically|kindly)\b", " ", t)
    return re.sub(r"\s+", " ", t).strip()


# Polite openings removed before matching: "can you explain this database" -> "explain this database".
_OPENING = re.compile(
    r"^(?:(?:okay|ok|so|now|well|alright|all right|and|then|also|hey|yo) )*"
    r"(?:(?:can|could|would|will) you (?:also )?|i (?:want|would like|wanna|need) (?:you )?to |"
    r"i (?:want|need|would like) to know |do you know |i wonder |i was wondering |"
    r"let us |let me (?:know |hear )?|go ahead and |try to )*")


def _strip_opening(t: str) -> str:
    stripped = _OPENING.sub("", t).strip()
    return stripped or t


_THIS_DB = r"(?:this|the current|the open|the|our|my|current|that) ?(?:database|data base|db)"

_HELP = re.compile(r"^(help( me)?|i need( some)? help|i am (lost|confused|stuck)|instructions|what can i (ask|say|do)( here| you)?|"
                   r"what (can|do) you do|how (do|does) (this|it|you) work|how do i use (this|it|you)|"
                   r"what do i do|what now|where do i start|how do i (start|begin|ask( a question)?)|"
                   r"what questions can i ask|what things can i ask|what commands are there|commands)$")
_EXAMPLES = re.compile(r"^(examples?|an example|some examples|give me (an |some |a few )?(examples?|ideas?|suggestions?)|"
                       r"(any )?(ideas|suggestions)|suggest (something|a question|some questions)|"
                       r"what should i (ask|say|try)( next)?|what (else )?can i (try|ask next)|surprise me|"
                       r"what is a good question|show me what you can do)$")
_LIST_DBS = re.compile(r"^(what|which|how many) (other )?databases( are there| do (i|we|you) have| are available| are loaded|"
                       r" are registered| can i (use|ask about|open)| are on (this|my) computer)?$|"
                       r"^(list|show|name|read|tell)( me)?( the| my| all| all the| all of the| available| other)* databases$|"
                       r"^(the |all |all the |my |other |any other )?databases$|"
                       r"^(are there|do (you|i|we) have) (any )?(other |more )?databases$")
_CURRENT = re.compile(r"^(what|which) database (am i (in|on|using)|is (this|open|current|loaded|selected|active|it)|"
                      r"are we (in|on|using)|is open( right now| now)?)$|^(the )?current database$|^where am i$|"
                      r"^what am i (looking at|in|using)$|^which one is open$")
_DESCRIBE_DB = re.compile(
    r"^(explain|describe|tell me about|what is in|summarize|summarise|give me an overview of|overview of|"
    r"what do (i|we) have in|what is|walk me through|go over|break down) " + _THIS_DB + r"$|"
    r"^(what|which) tables( are there| are in " + _THIS_DB + r"| does (it|this|this database) have| do (i|we|you) have| can i ask about)?$|"
    r"^(list|show|show me|read|name|tell me)( the| all| all the)? tables( in " + _THIS_DB + r")?$|"
    r"^what can i ask about " + _THIS_DB + r"$|^what is " + _THIS_DB + r" about$|^what does " + _THIS_DB + r" (have|contain|hold)$")
_DESCRIBE_SHORT = re.compile(
    r"^(explain|describe|overview|summary|summarize|summarise|details|info|information|rundown|"
    r"explain (it|this|that|everything|all|all of it|the data|this data|things|what is here)|"
    r"describe (it|this|that|everything|the data|what is here)|"
    r"tell me (about it|about this|about that|everything|about the data|what is here|what is in here)|"
    r"give me (a |an )?(rundown|overview|summary|tour)|"
    r"what is (this|here|in here|in it|in there|available)|what is this about|"
    r"what data (is there|do (you|i|we) have|is here|is available|is in here)|"
    r"what (kind|kinds|sort|type|types) of (data|information|stuff|things) (is there|do you have|is here|are there|"
    r"can i ask about|is in here)|what do you (have|know|know about)|what have you got|what is in the data)$")
_DESCRIBE_NAMED_DB = re.compile(r"^(explain|describe|tell me about|what is in|summarize|summarise|overview of|"
                                r"what tables are in|what is|walk me through) (the )?(?P<name>[\w\- ]+?) (database|data base|db)$")
_LIST_TABLES = re.compile(r"^((the |all |all the )?tables|how many tables( are there| do (you|i|we) have| does it have| are in it)?|"
                          r"what are the tables|which tables|tables please)$")
_COLUMNS_SHORT = re.compile(r"^((the |all |all the )?(columns|fields)|what (columns|fields)( are there| do (you|i|we) have| does it have| are available)?|"
                            r"(list|show|read|name|tell)( me)?( the| all| all the)? (columns|fields)|what are the (columns|fields))$")
_DESCRIBE_TABLE = re.compile(
    r"^(explain|describe|tell me about|tell me more about|more about|what is in|summarize|summarise|walk me through|"
    r"what columns (are|do you have|does .* have|are there) in|what columns (are in|does)|which columns (are in|does)|"
    r"(list|show|read|tell)( me)?( the)? columns (in|of|for)|what fields (are in|does)|what can i ask about|"
    r"what is the (shape|structure|layout) of|what does .* look like in|what is the deal with) (the )?(?P<name>[\w\- ]+?)( table)?( have| contain| look like)?$")
_SWITCH = re.compile(r"^(switch|change|go|move|swap|jump|head) (over |back )?to (the )?(?P<name>[\w\- ]+?)( database| db| one)?$|"
                     r"^(open|use|load|select|choose|pick|try) (the )?(?P<name2>[\w\- ]+?) (database|db)( instead)?$|"
                     r"^(open|use|load) (the )?(?P<name3>[\w\- ]+)$")
_ADD = re.compile(r"^(add|register|import|attach|load up|open|connect|bring in) (a |an |another |a new |new |my )?(database|data base|db|file|database file)"
                  r"( from (a )?file)?$|^new database$|^(i want to |how do i )?add (a )?database$")
_FOLLOW_UP = re.compile(r"^(what about|how about|and what about|and|what of|now|then) (the )?(?P<name>[\w\- ]+?)( table| database| db| then)?$")
_MORE = re.compile(r"^(more|tell me more|go on|continue|keep going|and then|what else|anything else|keep reading|more results|"
                   r"more rows|read more|tell me more about (it|that|this)|more please|more details|go deeper)$")
_RESULTS = re.compile(r"^(results|the results|what (are|were) the results|what did you find|what did it find|"
                      r"read (the |me the )?results|read (it|them)|answer|the answer|what is the answer|tell me the (results|answer)|"
                      r"what came back|what did you get|so what is the answer)$")
_FIRST_LAST = re.compile(r"^(read |go to )?(the )?(?P<which>first|last|top|bottom|final) (row|result|one|record|answer)$")
_REPEAT = re.compile(r"^(repeat|repeat that|say (that|it) again|say again|again|pardon|pardon me|what did you say|"
                     r"come again|one more time|read that again|sorry what|what|huh|i did not (catch|hear|get) that)$")
_READ_ROW = re.compile(r"^(read|say|tell me|give me|show me|what is|go to)( the)? (row|result|line|record|item|number|answer) "
                       r"(number )?(?P<n>\d+|" + "|".join(NUMBER_WORDS) + r")$|"
                       r"^(row|result|line|record|number) (number )?(?P<n2>\d+|" + "|".join(NUMBER_WORDS) + r")$|"
                       r"^(read |what is )?the (?P<n3>" + "|".join(k for k in NUMBER_WORDS if k.endswith(("st", "nd", "rd", "th"))) +
                       r") (row|result|one|record)$")
_NEXT = re.compile(r"^(next|next (row|result|one|line|record|answer)|go (forward|down)|move (on|down)|the next one|and the next|what is next)$")
_PREVIOUS = re.compile(r"^(previous|previous (row|result|one|line|record)|back|go back|go up|the one before|the previous one)$")
_READ_ALL = re.compile(r"^(read|say|tell me|give me)( me)?( all| all the| all of the| every| the)? (results|rows|answers|records)"
                       r"( out loud| aloud| to me)?$|^read (them|it) all$|^read everything$|^(all|every) (results|rows)$")
_ROW_COUNT = re.compile(r"^how many (rows|results|records|answers|matches)( (are there|did (i|you|we) get|came back|were found|"
                        r"are in the results|match|matched|did it find))?$|^(number|count) of (rows|results)$")
_LAST_Q = re.compile(r"^(what (did|was) (i|my) (ask|say|question|last question)( again)?|repeat (my|the) question|"
                     r"what was the question|what did you hear|what did i (just )?(ask|say)|what was my question)$")
_CANCEL = re.compile(r"^(cancel|stop|never mind|nevermind|forget it|nothing|stop listening|quiet|be quiet|stop talking|shut up|"
                     r"silence|hush|enough|that is enough|okay stop)$")
_GREETING = re.compile(r"^(hi|hello|hey|howdy|greetings|yo|good (morning|afternoon|evening|day))( there| voice database query| computer| friend)?$")
_THANKS = re.compile(r"^(thank you|thanks|thank you (so|very) much|thanks (a lot|so much|a bunch)|much appreciated|appreciate it|"
                     r"great|awesome|perfect|cool|nice|good job|well done|excellent|wonderful|that is great|that helps|got it)$")
_ABOUT = re.compile(r"^(who are you|what are you|what is your name|who am i talking to|what is this( program| app| application)?|"
                    r"what does this (program|app|application) do|tell me about (yourself|you|this program|this app|this application)|"
                    r"what can this (program|app) do|are you (a robot|a computer|an ai|human|a person|chat ?gpt|claude))$")
_HOW = re.compile(r"^(how are you( doing| today)?|how is it going|how are things|how do you do|"
                  r"are you (there|listening|working|ready|awake|ok|okay)|can you hear me|is this (working|on)|testing( testing)?)$")
_YES = re.compile(r"^(yes|yeah|yep|yup|yes i do|yes please|sure|of course|do it|go ahead|please do|affirmative|correct|right|"
                  r"definitely|absolutely|ok|okay|i am sure)$")
_NO = re.compile(r"^(no|nope|nah|no thanks|no thank you|do not|not now|cancel that|i changed my mind|stay|keep it open)$")
_EXIT = re.compile(r"^(exit|quit|close|leave|end|shut down|shut) (the |this )?(program|app|application|voice database query|"
                   r"database query|window)( now)?$|^(exit|quit) now$")
_CONFIRM_EXIT = re.compile(r"^(exit|quit|close|goodbye|good bye|bye|bye bye|see you|see you later|see ya|good night|"
                           r"i am done|that is all|that is it|i am finished|we are done|i am leaving|end)$")

_EXPLAIN_WORDS = {"explain", "describe", "overview", "summary", "summarize", "summarise", "structure", "schema",
                  "layout", "rundown", "breakdown", "tour", "contents"}   # not "contains": that is a data word


def _spoken(name: str) -> str:
    return name.lower().replace("_", " ").strip()


def _mentioned_table(t: str, table_names) -> "str | None":
    """The table named in the sentence, longest name first, allowing a dropped or added s."""
    words = f" {t} "
    for name in sorted(table_names, key=lambda n: -len(n)):
        s = _spoken(name)
        forms = {s, s.rstrip("s"), s + "s", name.lower()}
        if any(f and f" {f} " in words for f in forms):
            return name
    return None


def _mentioned_database(t: str, database_names) -> "str | None":
    words = f" {t} "
    for name in sorted(database_names, key=lambda n: -len(n)):
        low = name.lower()
        if f" {low} " in words:
            return name
        first = low.split()[0] if low.split() else ""
        if len(first) > 2 and f" {first} " in words:
            return name
    return None


def _keywords(t: str, database_names, table_names) -> "Command | None":
    """Layer 3: loose wording, using the real names. Data questions are left alone."""
    words = set(t.split())
    table = _mentioned_table(t, table_names)
    database = _mentioned_database(t, database_names)
    explaining = bool(words & _EXPLAIN_WORDS) or "tell me about" in t or "what is in" in t
    if table and not explaining and not (words & {"columns", "column", "fields", "field"}):
        return None                                  # a question about the data: the grammar takes it
    if database and words & {"switch", "change", "open", "use", "load", "swap", "jump"} and not table:
        return Command(SWITCH_DATABASE, database)
    if "databases" in words and not table:
        return Command(LIST_DATABASES)
    if table and (explaining or words & {"columns", "column", "fields", "field"}):
        return Command(DESCRIBE_TABLE, table)
    if database and (explaining or "about" in words):
        return Command(DESCRIBE_DATABASE, database)
    if words & {"database", "db"} and (explaining or words & {"about", "this", "current", "what", "which"}):
        return Command(DESCRIBE_DATABASE, None)
    if words & {"columns", "fields"}:
        return Command(COLUMNS)
    if "tables" in words:
        return Command(DESCRIBE_DATABASE if explaining else LIST_TABLES)
    if explaining:
        return Command(DESCRIBE_DATABASE, None)
    if words & {"help", "confused", "lost", "stuck", "instructions"}:
        return Command(HELP)
    if words & {"example", "examples", "suggestion", "suggestions", "ideas"}:
        return Command(EXAMPLES)
    return None


def _row_number(raw: str) -> "int | None":
    if raw.isdigit():
        return int(raw)
    return NUMBER_WORDS.get(raw)


def detect(text: str, database_names=(), table_names=()) -> "Command | None":
    """Decide whether the text is something said to the program. None means: a data question.

    database_names and table_names are the registered databases and the open database's tables;
    they let loose wording and follow-ups be understood.
    """
    t = _clean(text)
    if not t:
        return None
    t = _strip_opening(t)

    # Layer 1 and 2: phrases. Order matters where phrases overlap.
    simple = ((_GREETING, GREETING), (_THANKS, THANKS), (_ABOUT, ABOUT), (_HOW, HOW_ARE_YOU),
              (_EXAMPLES, EXAMPLES), (_HELP, HELP), (_LIST_DBS, LIST_DATABASES), (_CURRENT, CURRENT_DATABASE),
              (_LAST_Q, LAST_QUESTION), (_REPEAT, REPEAT), (_NEXT, NEXT_ROW), (_PREVIOUS, PREVIOUS_ROW),
              (_ROW_COUNT, ROW_COUNT), (_READ_ALL, READ_ALL), (_RESULTS, READ_RESULTS), (_MORE, MORE),
              (_LIST_TABLES, LIST_TABLES), (_COLUMNS_SHORT, COLUMNS), (_ADD, ADD_DATABASE), (_EXIT, EXIT),
              (_CONFIRM_EXIT, CONFIRM_EXIT), (_YES, YES), (_NO, NO), (_CANCEL, CANCEL))
    for pattern, kind in simple:
        if pattern.match(t):
            return Command(kind)
    m = _FIRST_LAST.match(t)
    if m:
        return Command(READ_ROW, 1 if m.group("which") in ("first", "top") else -1)
    m = _READ_ROW.match(t)
    if m:
        number = _row_number(m.group("n") or m.group("n2") or m.group("n3"))
        if number is not None:
            return Command(READ_ROW, number)
    if _DESCRIBE_DB.match(t) or _DESCRIBE_SHORT.match(t):
        return Command(DESCRIBE_DATABASE, None)
    m = _DESCRIBE_NAMED_DB.match(t)
    if m:
        return Command(DESCRIBE_DATABASE, m.group("name").strip())
    m = _SWITCH.match(t)
    if m:
        name = (m.group("name") or m.group("name2") or m.group("name3")).strip()
        # "open the players" or "use points" are data words, not databases, when we know the names
        if not (m.group("name3") and table_names and _mentioned_table(name, table_names)):
            return Command(SWITCH_DATABASE, name)
    m = _DESCRIBE_TABLE.match(t)
    if m:
        name = m.group("name").strip()
        if database_names and _mentioned_database(name, database_names) and not _mentioned_table(name, table_names):
            return Command(DESCRIBE_DATABASE, _mentioned_database(name, database_names))
        return Command(DESCRIBE_TABLE, name)
    m = _FOLLOW_UP.match(t)
    if m:
        return Command(FOLLOW_UP, m.group("name").strip())

    # Layer 3: keywords.
    return _keywords(t, database_names, table_names)


# Spoken answers. All pure functions of plain data.

def plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _join(items) -> str:
    items = list(items)
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def _spoken_name(name: str) -> str:
    """Table and column names as they would be said: player_season_stats -> player season stats."""
    return name.replace("_", " ")


def example_questions(schema: "Schema | None", limit: int = 3) -> list:
    """Questions that will work on this schema, built from its own table and column names."""
    if schema is None or not schema.tables:
        return []
    tables = list(schema.tables.values())
    named = [t for t in tables if t.label_column] or tables
    first = named[0]
    out = [f"show the first 5 {_spoken_name(first.name)}", f"how many {_spoken_name(first.name)} are there"]
    for t in tables:
        numeric = [c.name for c in t.columns if c.is_numeric and not c.primary_key
                   and not schema.is_foreign_key_column(t.name, c.name)]
        if numeric:
            out.append(f"top 5 {_spoken_name(t.name)} by {_spoken_name(numeric[0])}")
            out.append(f"what is the average {_spoken_name(numeric[0])} in {_spoken_name(t.name)}")
            break
    for t in tables:
        if t.label_column:
            out.append(f"{_spoken_name(t.name)} sorted by {_spoken_name(t.label_column)}")
            break
    return out[:limit]


def help_text(current_name: "str | None", schema: "Schema | None") -> str:
    parts = ["Press Enter and speak after the beep. I listen until you pause; a double beep means I heard you, "
             "then I answer. Press Escape to stop listening."]
    if schema is not None and current_name:
        parts.append(f"You are asking about the {current_name} database, which has {plural(len(schema.tables), 'table')}: "
                     f"{_join(_spoken_name(n) for n in schema.table_names)}.")
        examples = example_questions(schema)
        if examples:
            parts.append("For example, say: " + "; or ".join(examples) + ".")
    else:
        parts.append("No database is open. Say add a database, or press Tab to reach the Add database button.")
    parts.append("You can also talk to me about the program: say explain, to hear about this database; "
                 "what databases are there; describe, and a table name; switch to, and a database name; "
                 "read row 3; next; tell me more; repeat; or goodbye. For typing instead, press Control plus T.")
    return " ".join(parts)


def examples_text(current_name: "str | None", schema: "Schema | None") -> str:
    examples = example_questions(schema, limit=5)
    if not examples:
        return "Open a database first, then I can suggest questions. Say add a database."
    return f"Here are some questions for the {current_name} database: " + "; ".join(examples) + "."


def databases_text(names: list, current_name: "str | None") -> str:
    if not names:
        return "No databases are registered yet. Say add a database to choose a file."
    sentence = f"There {'is' if len(names) == 1 else 'are'} {plural(len(names), 'database')}: {_join(names)}."
    if current_name:
        sentence += f" {current_name} is open now."
    if len(names) > 1:
        sentence += " Say switch to, then a name, to change."
    return sentence


def current_database_text(current_name: "str | None", schema: "Schema | None") -> str:
    if not current_name or schema is None:
        return "No database is open. Say add a database, or say switch to and a database name."
    return (f"The current database is {current_name}. It has {plural(len(schema.tables), 'table')}: "
            f"{_join(_spoken_name(n) for n in schema.table_names)}.")


def tables_text(current_name: "str | None", schema: "Schema | None") -> str:
    if not current_name or schema is None:
        return "No database is open, so there are no tables yet. Say add a database."
    return (f"{current_name} has {plural(len(schema.tables), 'table')}: {_join(_spoken_name(n) for n in schema.table_names)}. "
            "Say describe, and a table name, to hear its columns.")


def database_text(name: str, schema: Schema) -> str:
    """Explain a database: each table with its column count and a few column names, then examples."""
    tables = list(schema.tables.values())
    if not tables:
        return f"The {name} database has no tables."
    bits = []
    for t in tables:
        cols = [_spoken_name(c) for c in t.column_names]
        shown = _join(cols) if len(cols) <= 6 else ", ".join(cols[:5]) + f", and {len(cols) - 5} more"
        bits.append(f"{_spoken_name(t.name)}, with {plural(len(cols), 'column')}: {shown}")
    links = sorted({f"{_spoken_name(fk.from_table)} links to {_spoken_name(fk.to_table)}" for fk in schema.foreign_keys})
    text = f"The {name} database has {plural(len(tables), 'table')}. " + ". ".join(bits) + "."
    if links:
        text += " Connections: " + _join(links) + "."
    examples = example_questions(schema)
    if examples:
        text += " Try: " + "; or ".join(examples) + "."
    return text


def table_text(table: Table, schema: Schema) -> str:
    cols = []
    for c in table.columns:
        kind = "number" if c.is_numeric else "text"
        note = ""
        if c.primary_key:
            note = ", the key"
        elif schema.is_foreign_key_column(table.name, c.name):
            note = ", a link to another table"
        cols.append(f"{_spoken_name(c.name)}, {kind}{note}")
    text = f"The {_spoken_name(table.name)} table has {plural(len(table.columns), 'column')}: " + "; ".join(cols) + "."
    related = sorted({fk.to_table for fk in schema.foreign_keys if fk.from_table.lower() == table.name.lower()} |
                     {fk.from_table for fk in schema.foreign_keys if fk.to_table.lower() == table.name.lower()})
    if related:
        text += f" It connects to {_join(_spoken_name(r) for r in related)}."
    numeric = [c.name for c in table.columns if c.is_numeric and not c.primary_key
               and not schema.is_foreign_key_column(table.name, c.name)]
    if numeric:
        text += f" For example: top 5 {_spoken_name(table.name)} by {_spoken_name(numeric[0])}."
    elif table.label_column:
        text += f" For example: {_spoken_name(table.name)} sorted by {_spoken_name(table.label_column)}."
    return text


def find_table(schema: "Schema | None", spoken: str) -> "Table | None":
    """Match a spoken name to a table: exact, then singular or plural, then contained."""
    if schema is None or not spoken:
        return None
    s = spoken.strip().lower().replace(" ", "_")
    s = re.sub(r"^(the_)", "", s)
    s = re.sub(r"_table$", "", s)
    exact = schema.table(s)
    if exact:
        return exact
    for t in schema.tables.values():
        n = t.name.lower()
        if n == s + "s" or n + "s" == s or n == s + "es" or n.rstrip("s") == s.rstrip("s"):
            return t
    for t in schema.tables.values():
        n = t.name.lower()
        if len(s) > 2 and (s in n or n in s):
            return t
    return None


def mentioned_table(schema: "Schema | None", text: str) -> "Table | None":
    """A table named anywhere in a sentence, for follow-ups and for explaining a failed question."""
    if schema is None:
        return None
    name = _mentioned_table(_clean(text), schema.table_names)
    return schema.table(name) if name else None


def not_understood_text(question: str, current_name: "str | None", schema: "Schema | None", reason: str = "") -> str:
    """When the data grammar fails: say so, repeat what was heard, and give working examples."""
    text = f"I heard: {question}. "
    text += reason.strip() + " " if reason else "I did not understand that as a question about the data. "
    table = mentioned_table(schema, question)
    if table is not None and "columns in" not in reason and "Did you mean" not in reason:
        text += (f"The {_spoken_name(table.name)} table has: "
                 f"{_join(_spoken_name(c) for c in table.column_names)}. ")
    examples = example_questions(schema, limit=2)
    if examples:
        text += "Try something like: " + "; or ".join(examples) + ". "
    text += "Or say help."
    return text.strip()


def greeting_text(current_name: "str | None", schema: "Schema | None") -> str:
    if schema is not None and current_name:
        example = (example_questions(schema, limit=1) or ["explain"])[0]
        return (f"Hello. I am ready to answer questions about the {current_name} database. "
                f"Press Enter and ask, for example: {example}.")
    return "Hello. Add a database first: say add a database, or press Tab to reach the Add database button."


ABOUT_TEXT = ("I am Voice Database Query. I answer spoken questions about the databases on this computer, "
              "like a chat assistant for your data. I only read your data; I never change it, and nothing you say "
              "leaves this computer. Say help to hear what you can ask.")
THANKS_TEXT = "You are welcome. Press Enter whenever you have another question."
HOW_ARE_YOU_TEXT = "I am working and listening. Press Enter and ask me something about your data."
CONFIRM_EXIT_TEXT = "Do you want to close Voice Database Query? Press Enter and say yes to close, or no to stay."
NOTHING_PENDING_YES = "Okay. Press Enter and ask me something about your data."
NOTHING_PENDING_NO = "Okay. Press Enter when you have a question."
