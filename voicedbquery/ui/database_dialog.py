"""Add a database: file picker, validation, then a name."""

import wx

from voicedbquery.data.connection import DatabaseFileError, validate_database_file

WILDCARD = "SQLite databases (*.db;*.sqlite;*.sqlite3)|*.db;*.sqlite;*.sqlite3|All files (*.*)|*.*"


def ask_for_database(parent):
    """Return (name, path) or None if cancelled. Raises DatabaseFileError for a bad file."""
    with wx.FileDialog(parent, "Choose a SQLite database", wildcard=WILDCARD,
                       style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dlg:
        if dlg.ShowModal() != wx.ID_OK:
            return None
        chosen = dlg.GetPath()
    path = validate_database_file(chosen)
    with wx.TextEntryDialog(parent, "Name for this database:", "Add database", value=path.stem) as dlg:
        if dlg.ShowModal() != wx.ID_OK:
            return None
        name = dlg.GetValue().strip() or path.stem
    return name, str(path)
