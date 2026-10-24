"""Command-line runner, for development and for Phase 0 testing without the interface.

Examples:
  python -m voicedbquery.cli --db samples/nba_5seasons.db "top 5 players by pts"
  python -m voicedbquery.cli --db samples/movies_small.db --sql "SELECT title FROM movies LIMIT 3"
"""

import argparse
import sys

from voicedbquery.config.catalog import Catalog
from voicedbquery.config.settings import Settings
from voicedbquery.data.executor import QueryError
from voicedbquery.engine import Engine, row_sentence, summary_sentence
from voicedbquery.logging_setup import setup_logging
from voicedbquery.query.intent import ParseError


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Ask a question about a local SQLite database.")
    parser.add_argument("--db", required=True, help="path to a .db, .sqlite, or .sqlite3 file")
    parser.add_argument("--sql", action="store_true", help="treat the text as a SELECT statement")
    parser.add_argument("--schema", action="store_true", help="print the tables and columns and exit")
    parser.add_argument("text", nargs="?", default="", help="the question or SQL")
    args = parser.parse_args(argv)

    setup_logging()
    engine = Engine(Settings(), Catalog())
    try:
        schema = engine.open_path(args.db)
        if args.schema:
            print(schema.describe())
            return 0
        outcome = engine.run_sql(args.text) if args.sql else engine.ask(args.text)
    except (ParseError, QueryError, ValueError) as exc:
        print(f"Sorry: {exc}", file=sys.stderr)
        return 1
    finally:
        engine.close()

    print(f"Understood as: {outcome.description}")
    print(f"SQL: {outcome.sql}  params={outcome.params}")
    print(summary_sentence(outcome.result))
    for i in range(outcome.result.row_count):
        print(row_sentence(outcome.result, i))
    return 0


if __name__ == "__main__":
    sys.exit(main())
