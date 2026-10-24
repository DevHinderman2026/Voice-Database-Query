"""Checks for SQL the user typed directly. Defense in depth only: the connection itself is
read-only, so even a statement that slips past here cannot change anything."""

import re
import sqlite3

from voicedbquery.query.intent import ParseError


def check_select(sql: str) -> str:
    text = re.sub(r"--[^\n]*", "", sql)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S).strip()
    if not text:
        raise ParseError("Type a SELECT statement first.")
    if not sqlite3.complete_statement(text.rstrip(";") + ";"):
        raise ParseError("That SQL is incomplete. Check for a missing quote or bracket.")
    body = text.rstrip(";").strip()
    if ";" in body:
        raise ParseError("Run one statement at a time.")
    first = body.split(None, 1)[0].lower()
    if first not in ("select", "with"):
        raise ParseError("Only SELECT statements can be run here. This application never changes data.")
    return body
