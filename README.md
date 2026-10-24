# Voice Database Query

Ask spoken questions about SQLite databases on your own computer, and hear the answers. Made for screen reader users first (NVDA, JAWS and Narrator).

Version 1.0. See Changelog.md for what is new.

## What it does

- Press Enter and speak after the beep, for example "top 5 players by points" or "how many movies are there". A double beep means you were heard, then the answer is spoken.
- Not sure what to ask? Say "explain", "what databases are there", "describe the players table", "give me some examples" or "help".
- Follow up the way you would in a conversation: "tell me more", "next", "read row 3", "what about teams", "repeat".
- Your data is only read, never changed. Speech recognition runs on your computer, and nothing you say or ask leaves it.

## Installing

1. Install Python 3.12, 3.13 or 3.14 from python.org if you do not have it.
2. Download this repository (Code, Download ZIP), and choose Extract All.
3. Run "Install or Update Voice Database Query". It installs what the program needs, including the speech model (about 1.8 gigabytes, once), and announces every 10 percent.
4. Run "Start Voice Database Query".

## Using it

When it starts it says: "Welcome to Voice Database Query. Press Enter to ask a question, or press Tab to add a database."

1. The first time, press Tab, then Enter on Add database, and choose a SQLite file (.db, .sqlite or .sqlite3).
2. Press Enter, wait for the beep, and ask your question.
3. Listen to the answer, or press Tab to read the Heard, Understood as, Results and Status areas.

Keys:

- Enter: ask by voice. Enter again finishes early.
- Escape: stop listening, or cancel a running question.
- Control plus T: type a question or a SELECT statement instead.
- Control plus R: read the current result row. Control plus Shift plus R: read all results.
- Control plus D: add a database.

## Safety

Every database is opened read-only, and three more checks stop anything that could change it. After installing, the program uses no network. Settings and history are kept in your AppData folder.

## Credits and license

Made by Russell Hinderman with Claude, an AI model made by Anthropic. Free software under the MIT License. See Credits.md for the projects it is built on.
