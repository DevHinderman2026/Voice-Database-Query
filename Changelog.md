# Voice Database Query release notes

## 1.0 (24 October 2026)

The first release. Voice Database Query lets you ask spoken questions about SQLite databases on your own computer and hear the answers, with a screen reader (NVDA, JAWS or Narrator).

### What it does

- Press Enter and speak after the beep. A double beep means you were heard; then the answer is spoken.
- Ask about your data in plain English: "top 5 players by points", "how many teams are there", "movies where rating is over 8", "average points in player season stats". Questions can reach a second linked table on their own.
- Talk to it about the program like a chat assistant: "explain", "what databases are there", "describe the players table", "switch to movies", "tell me more", "what about teams", "read row 3", "next", "repeat", "help".
- Spoken numbers work: "over one thousand two hundred", "after twenty ten", "seven point five".
- Name a database in a question ("... in the movies database") and it switches to it.
- Every answer is also shown in the window: what was heard, what it was understood as (with the SQL it ran), the results table and the status.
- Typing is still there for when the microphone is not available: Control plus T opens a box for a question or a SELECT statement.
- Add databases with Tab and Enter on Add database, or by saying "add a database".

### Safety and privacy

- Read-only by design: your databases are opened so they cannot be changed, and four separate checks enforce it.
- Speech recognition runs on your computer (Vosk). No audio, question or data leaves it. After installing, the program uses no network at all.
- Settings, the list of databases and the question history are kept in your AppData folder, never next to the program.

### Installing

- Install or Update Voice Database Query sets up a private Python environment, the packages, and the speech model (about 1.8 gigabytes, downloaded once), and says every 10 percent how far it has got. An interrupted download continues where it stopped.

### Known limits

- Questions use AND between conditions, not OR, and sort by one column.
- Very large results show the first 500 rows.
- English only.
