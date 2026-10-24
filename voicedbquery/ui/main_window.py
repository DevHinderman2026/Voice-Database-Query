"""The main window, voice first (decision D16).

Tab order equals layout order: Ask a question, Add database, Stop, Database list, Heard, Understood as,
Results, Status. Enter anywhere (except on a button, where it presses that button) starts listening.
Typing is a fallback behind Control plus T.
"""

import logging
import re
import threading

import wx

from voicedbquery import __version__
from voicedbquery.config.paths import models_dir
from voicedbquery.data.connection import DatabaseFileError
from voicedbquery.data.executor import QueryError
from voicedbquery.engine import Engine, Outcome, row_sentence, summary_sentence
from voicedbquery.query import assistant
from voicedbquery.query.intent import ParseError
from voicedbquery.ui.announcer import Announcer
from voicedbquery.ui.database_dialog import ask_for_database
from voicedbquery.ui.type_dialog import ask_typed
from voicedbquery.voice.audio_input import Microphone, MicrophoneError
from voicedbquery.voice import tones
from voicedbquery.voice.recognizer import ModelMissing, RecognitionError, Recognizer, find_model

log = logging.getLogger(__name__)

(ID_LISTEN, ID_CANCEL, ID_TYPE, ID_READ_ROW, ID_READ_ALL, ID_ADD_DB, ID_REMOVE_DB,
 ID_SHORTCUTS, ID_WHAT_TO_SAY) = [wx.NewIdRef() for _ in range(9)]

APP_TITLE = "Voice Database Query"
WELCOME = f"Welcome to {APP_TITLE}. Press Enter to ask a question, or press Tab to add a database."
SHORTCUTS = (
    "Enter: beep, then ask a question by voice; a double beep means you were heard. Press Enter again to finish early. Escape: stop listening or cancel a query. "
    "Tab: move to the Add database button and the other controls. Control plus T: type a question or SQL instead. "
    "Control plus R: read the current result row. Control plus Shift plus R: read all results. "
    "Control plus D: add a database. Alt plus the underlined letter jumps to a control."
)
IDLE, LOADING, LISTENING, RUNNING = "idle", "loading", "listening", "running"
READ_ALL_LIMIT = 10


class MainWindow(wx.Frame):
    def __init__(self, engine: Engine):
        super().__init__(None, title=APP_TITLE, size=(960, 680))
        self.engine = engine
        self.outcome: "Outcome | None" = None
        self.last_question = ""
        self._last_table: "str | None" = None   # the table being talked about, for "columns" and "tell me more"
        self._last_kind = ""                     # what the last reply was: results, database, table, help, error
        self._pending_exit = False               # "goodbye" asked; waiting for yes or no
        self._state = LOADING
        self._stop_listening = threading.Event()
        self._discard = False
        panel = wx.Panel(self)
        self.panel = panel

        self.ask_btn = wx.Button(panel, ID_LISTEN, "&Ask a question (press Enter, then speak)")
        self.add_btn = wx.Button(panel, ID_ADD_DB, "A&dd database")
        self.cancel_btn = wx.Button(panel, ID_CANCEL, "&Stop")
        self.cancel_btn.Disable()
        db_label = wx.StaticText(panel, label="Data&base:")
        self.db_choice = wx.Choice(panel, choices=engine.catalog.names())
        h_label = wx.StaticText(panel, label="&Heard:")
        self.heard = wx.TextCtrl(panel, style=wx.TE_READONLY | wx.TE_MULTILINE, size=(-1, 44))
        u_label = wx.StaticText(panel, label="&Understood as:")
        self.understood = wx.TextCtrl(panel, style=wx.TE_READONLY | wx.TE_MULTILINE, size=(-1, 44))
        r_label = wx.StaticText(panel, label="R&esults:")
        self.results = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        s_label = wx.StaticText(panel, label="S&tatus:")
        self.status = wx.TextCtrl(panel, style=wx.TE_READONLY | wx.TE_MULTILINE, size=(-1, 72))
        self.announcer = Announcer(self.status, engine.settings, self.GetHandle)

        buttons = wx.BoxSizer(wx.HORIZONTAL)
        for b in (self.ask_btn, self.add_btn, self.cancel_btn):
            buttons.Add(b, 0, wx.RIGHT, 8)
        sizer = wx.BoxSizer(wx.VERTICAL)
        for item, flag in ((buttons, 0), (db_label, 0), (self.db_choice, 0), (h_label, 0), (self.heard, 0),
                           (u_label, 0), (self.understood, 0), (r_label, 0), (self.results, 1),
                           (s_label, 0), (self.status, 0)):
            sizer.Add(item, flag, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 8)
        panel.SetSizer(sizer)

        self._build_menu()
        self.SetAcceleratorTable(wx.AcceleratorTable([
            (wx.ACCEL_CTRL, ord("L"), int(ID_LISTEN)), (wx.ACCEL_CTRL, ord("T"), int(ID_TYPE)),
            (wx.ACCEL_CTRL, ord("R"), int(ID_READ_ROW)), (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord("R"), int(ID_READ_ALL)),
            (wx.ACCEL_CTRL, ord("D"), int(ID_ADD_DB)),
        ]))
        for event_type in (wx.EVT_BUTTON, wx.EVT_MENU):
            self.Bind(event_type, self.on_listen, id=ID_LISTEN)
            self.Bind(event_type, self.on_cancel, id=ID_CANCEL)
            self.Bind(event_type, self.on_add_db, id=ID_ADD_DB)
        self.Bind(wx.EVT_MENU, self.on_type, id=ID_TYPE)
        self.Bind(wx.EVT_MENU, self.on_read_row, id=ID_READ_ROW)
        self.Bind(wx.EVT_MENU, self.on_read_all, id=ID_READ_ALL)
        self.Bind(wx.EVT_MENU, self.on_remove_db, id=ID_REMOVE_DB)
        self.Bind(wx.EVT_MENU, self.on_shortcuts, id=ID_SHORTCUTS)
        self.Bind(wx.EVT_MENU, self.on_what_to_say, id=ID_WHAT_TO_SAY)
        self.Bind(wx.EVT_MENU, lambda e: self.Close(), id=wx.ID_EXIT)
        self.Bind(wx.EVT_MENU, self.on_about, id=wx.ID_ABOUT)
        self.Bind(wx.EVT_CHOICE, self.on_choose_db, self.db_choice)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        self.Bind(wx.EVT_CLOSE, self.on_close)

        self.ask_btn.SetFocus()
        opened = self._open_initial()
        self._start_model_load()
        # after the screen reader has read the focused button, so the welcome is not cut short
        wx.CallLater(900, self._welcome, opened)

    def _build_menu(self):
        bar = wx.MenuBar()
        file_menu = wx.Menu()
        file_menu.Append(ID_ADD_DB, "&Add database...\tCtrl+D")
        file_menu.Append(ID_REMOVE_DB, "&Remove current database")
        file_menu.AppendSeparator()
        file_menu.Append(wx.ID_EXIT, "E&xit")
        query_menu = wx.Menu()
        query_menu.Append(ID_LISTEN, "&Ask by voice\tCtrl+L")
        query_menu.Append(ID_CANCEL, "&Stop listening or cancel\tEsc")
        query_menu.Append(ID_TYPE, "&Type a question or SQL...\tCtrl+T")
        query_menu.AppendSeparator()
        query_menu.Append(ID_READ_ROW, "Read current &row\tCtrl+R")
        query_menu.Append(ID_READ_ALL, "Read a&ll results\tCtrl+Shift+R")
        help_menu = wx.Menu()
        help_menu.Append(ID_WHAT_TO_SAY, "&What can I say")
        help_menu.Append(ID_SHORTCUTS, "&Keyboard shortcuts")
        help_menu.Append(wx.ID_ABOUT, "&About")
        bar.Append(file_menu, "&File")
        bar.Append(query_menu, "&Query")
        bar.Append(help_menu, "&Help")
        self.SetMenuBar(bar)

    # Startup

    def _welcome(self, opened: bool):
        text = WELCOME
        if opened and self.engine.schema is not None:
            text += (f" The current database is {self.engine.current_name}, with tables "
                     f"{', '.join(self.engine.schema.table_names)}.")
        elif self.engine.catalog.names():
            text += " No database could be opened."
        else:
            text += " No database is registered yet."
        if self._state == LOADING:
            text += " Speech is loading."
        self.announcer.announce(text)

    def _start_model_load(self):
        self.recognizer = Recognizer(find_model(models_dir()))

        def work():
            self.recognizer.load()
            wx.CallAfter(self._model_loaded)

        threading.Thread(target=work, daemon=True, name="speech-model").start()

    def _model_loaded(self):
        if self._state == LOADING:
            self._state = IDLE
        if self.recognizer.ready:
            self.announcer.announce("Speech is ready.", interrupt=False)
        else:
            self.announcer.announce(self.recognizer.load_error or "Speech is not available.", interrupt=False)

    # Databases

    def _open_initial(self) -> bool:
        names = self.engine.catalog.names()
        if not names:
            return False
        wanted = self.engine.settings.last_database
        index = names.index(wanted) if wanted in names else 0
        self.db_choice.SetSelection(index)
        return self._open_named(names[index], announce=False)

    def _open_named(self, name, announce=True) -> bool:
        try:
            schema = self.engine.open(name)
        except (DatabaseFileError, ParseError, QueryError) as exc:
            self.announcer.announce(f"Could not open {name}: {exc}")
            return False
        self.engine.settings.last_database = name
        self.engine.settings.save()
        self.outcome = None
        self._last_table = None
        self._last_kind = ""
        self.results.ClearAll()
        if announce:
            self.announcer.announce(f"Opened {name}. Tables: {', '.join(schema.table_names)}. Press Enter to ask a question.")
        return True

    def _select_in_list(self, name):
        names = self.engine.catalog.names()
        if name in names:
            self.db_choice.SetSelection(names.index(name))

    def on_choose_db(self, event):
        name = self.db_choice.GetStringSelection()
        if name:
            self.understood.SetValue(f"Open the {name} database.")
            self._open_named(name)

    def on_add_db(self, event):
        if self._state in (LISTENING, RUNNING):
            self.announcer.announce("Please wait until the current question is finished.")
            return
        try:
            chosen = ask_for_database(self)
        except DatabaseFileError as exc:
            self.announcer.announce(str(exc))
            return
        if not chosen:
            self.announcer.announce("No database was added.")
            return
        name, path = chosen
        try:
            self.engine.catalog.add(name, path)
        except ValueError as exc:
            self.announcer.announce(str(exc))
            return
        self.engine.catalog.save()
        self.db_choice.Append(name)
        self.db_choice.SetSelection(self.db_choice.GetCount() - 1)
        self._open_named(name)
        self.ask_btn.SetFocus()

    def on_remove_db(self, event):
        name = self.db_choice.GetStringSelection()
        if not name:
            return
        with wx.MessageDialog(self, f"Remove {name} from the list? The file itself is not touched.",
                              "Remove database", wx.YES_NO | wx.NO_DEFAULT) as dlg:
            if dlg.ShowModal() != wx.ID_YES:
                return
        self.engine.catalog.remove(name)
        self.engine.catalog.save()
        self.engine.close()
        self.db_choice.Delete(self.db_choice.GetSelection())
        self.db_choice.SetItems(self.engine.catalog.names())
        opened = self._open_initial()
        self.announcer.announce(f"Removed {name}." + (f" Now using {self.engine.current_name}." if opened else
                                                      " No database is open."))

    # Keys

    def on_key(self, event):
        key = event.GetKeyCode()
        focus = self.FindFocus()
        if key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and not event.HasAnyModifiers():
            if isinstance(focus, wx.Button) and focus is not self.ask_btn:
                event.Skip()      # Enter on Add database or Stop presses that button
                return
            self.on_listen(None)
            return
        if key == wx.WXK_ESCAPE:
            self.on_cancel(None)
            return
        event.Skip()

    # Listening

    def on_listen(self, event):
        if self._state == LISTENING:
            self._stop_listening.set()   # silent: the heard beep confirms, and speech now would be recorded
            return
        if self._state == RUNNING:
            self.announcer.announce("A query is running. Press Escape to cancel it.")
            return
        if self._state == LOADING:
            self.announcer.announce("Speech is still loading. Try again in a moment.")
            return
        if not self.recognizer.ready:
            self.announcer.announce(self.recognizer.load_error or "Speech is not available. Press Control plus T to type.")
            return
        self._state = LISTENING
        self._discard = False
        self._stop_listening = threading.Event()
        self.cancel_btn.Enable()
        self.heard.SetValue("")
        self.understood.SetValue("")
        beeps = self.engine.settings.listening_beeps
        if beeps:
            self.announcer.speaker.silence()   # the screen reader stops talking so the beep and the question are clear
        else:
            self.announcer.announce("Listening.")
        seconds = max(3, int(self.engine.settings.listen_seconds))

        def work():
            try:
                if beeps:
                    tones.play_start()         # finishes before the microphone opens, so it is not recorded
                with Microphone() as mic:
                    text = self.recognizer.listen(mic, self._stop_listening, max_seconds=seconds)
                if beeps and text.strip() and not self._discard:
                    tones.play_heard()         # microphone is closed; then the speech comes
                wx.CallAfter(self._heard, text)
            except (MicrophoneError, ModelMissing, RecognitionError) as exc:
                wx.CallAfter(self._listen_failed, str(exc))
            except Exception as exc:  # noqa: BLE001 - anything unexpected still reaches the user in plain words
                log.exception("Unexpected error while listening")
                wx.CallAfter(self._listen_failed, f"Listening failed: {exc}")

        threading.Thread(target=work, daemon=True, name="listen").start()

    def _listen_failed(self, message):
        self._state = IDLE
        self.cancel_btn.Disable()
        self.announcer.announce(message + " You can press Control plus T to type instead.")

    def _heard(self, text):
        self._state = IDLE
        self.cancel_btn.Disable()
        if self._discard:
            self.announcer.announce("Cancelled.")
            return
        text = re.sub(r"^(listening|finishing)\b\s*", "", text.strip(), flags=re.IGNORECASE)
        if not text:
            self.understood.SetValue("Nothing was heard.")
            self.announcer.announce("I did not hear anything. Press Enter and speak after the beep.")
            return
        self.heard.SetValue(text)
        self.handle_text(text, spoken=True)

    def on_cancel(self, event):
        if self._state == LISTENING:
            self._discard = True
            self._stop_listening.set()
            return
        if self._state == RUNNING:
            self.engine.cancel()
            self.announcer.announce("Cancelling.")

    # Questions and commands

    def handle_text(self, text: str, spoken: bool, use_sql: bool = False):
        """Everything heard or typed comes here: a command to the program, or a question about the data."""
        if use_sql:
            self._run(text, use_sql=True, spoken=False)
            return
        schema = self.engine.schema
        command = assistant.detect(text, self.engine.catalog.names(), schema.table_names if schema else [])
        if self._pending_exit:
            self._pending_exit = False
            if command is not None and command.kind in (assistant.YES, assistant.EXIT, assistant.CONFIRM_EXIT):
                self._close_now()
                return
            if command is not None and command.kind in (assistant.NO, assistant.CANCEL):
                self.understood.SetValue("No: stay open.")
                self.announcer.announce("Okay, I will stay open. Press Enter when you have a question.")
                return
        if command is not None:
            self.understood.SetValue(assistant.describe_command(command))
            self._do_command(command, text)
            return
        self._ask_data(text, spoken)

    def _ask_data(self, text: str, spoken: bool, note: str = ""):
        # "show players in the movies database": switch first, so the question reaches the right tables
        named = self.engine.database_named_in(text)
        if named and named != self.engine.current_name:
            self._select_in_list(named)
            if self._open_named(named, announce=False):
                note = f"Switched to {named}. " + note
        self._run(text, use_sql=False, spoken=spoken, note=note)

    def _run(self, text: str, use_sql: bool, spoken: bool, note: str = ""):
        if not self.engine.is_open:
            self.understood.SetValue("A question about the data, but no database is open.")
            self.announcer.announce("Open a database first. Say add a database, or press Tab to reach the Add database button.")
            return
        self._state = RUNNING
        self.last_question = text
        self.cancel_btn.Enable()
        self.understood.SetValue("Working it out.")
        self.announcer.announce(f"{note}I heard: {text}. Running." if spoken else f"{note}Running.")

        def work():
            try:
                outcome = self.engine.run_sql(text) if use_sql else self.engine.ask(text)
                wx.CallAfter(self._show_outcome, outcome, note)
            except (ParseError, QueryError, DatabaseFileError) as exc:
                reason = str(exc)
                if not use_sql:
                    message = assistant.not_understood_text(text, self.engine.current_name, self.engine.schema, reason)
                else:
                    message = reason
                wx.CallAfter(self._show_error, message, reason)
            except Exception as exc:  # noqa: BLE001
                log.exception("Unexpected error running query")
                wx.CallAfter(self._show_error, f"Something went wrong: {exc}", str(exc))

        threading.Thread(target=work, daemon=True, name="query").start()

    def _finish(self):
        self._state = IDLE
        self.cancel_btn.Disable()

    def _show_error(self, message, reason=""):
        self._finish()
        self.understood.SetValue("Not understood. " + (reason or message))
        self._last_kind = "error"
        self.announcer.announce(message)
        self.ask_btn.SetFocus()

    def _show_outcome(self, outcome: Outcome, prefix: str = ""):
        self._finish()
        self.outcome = outcome
        self._last_kind = "results"
        if outcome.intent is not None:
            self._last_table = outcome.intent.table
        self.understood.SetValue(outcome.description + (f" SQL: {outcome.sql}" if outcome.sql else ""))
        result = outcome.result
        self.results.ClearAll()
        for i, col in enumerate(result.columns):
            self.results.InsertColumn(i, col, width=140)
        for r, row in enumerate(result.rows):
            self.results.InsertItem(r, "" if row[0] is None else str(row[0]))
            for c, val in enumerate(row[1:], start=1):
                self.results.SetItem(r, c, "" if val is None else str(val))
        if result.row_count:
            self.results.Select(0)
            self.results.Focus(0)
            follow = " Say next, tell me more, or read all results. Or press Enter for another question."
        else:
            follow = " Press Enter to ask something else, or say help."
        self.announcer.announce(f"{prefix}{outcome.description} {summary_sentence(result)}{follow}")
        self.ask_btn.SetFocus()

    def _do_command(self, command, text):
        kind, arg = command.kind, command.argument
        engine, a = self.engine, self.announcer
        if kind == assistant.HELP:
            self._last_kind = "help"
            a.announce(assistant.help_text(engine.current_name, engine.schema))
        elif kind == assistant.EXAMPLES:
            self._last_kind = "help"
            a.announce(assistant.examples_text(engine.current_name, engine.schema))
        elif kind == assistant.GREETING:
            a.announce(assistant.greeting_text(engine.current_name, engine.schema))
        elif kind == assistant.THANKS:
            a.announce(assistant.THANKS_TEXT)
        elif kind == assistant.ABOUT:
            a.announce(assistant.ABOUT_TEXT)
        elif kind == assistant.HOW_ARE_YOU:
            a.announce(assistant.HOW_ARE_YOU_TEXT)
        elif kind == assistant.YES:
            a.announce(assistant.NOTHING_PENDING_YES)
        elif kind == assistant.NO:
            a.announce(assistant.NOTHING_PENDING_NO)
        elif kind == assistant.LIST_DATABASES:
            a.announce(assistant.databases_text(engine.catalog.names(), engine.current_name))
        elif kind == assistant.CURRENT_DATABASE:
            a.announce(assistant.current_database_text(engine.current_name, engine.schema))
        elif kind == assistant.LIST_TABLES:
            a.announce(assistant.tables_text(engine.current_name, engine.schema))
        elif kind == assistant.DESCRIBE_DATABASE:
            self._describe_database(arg)
        elif kind == assistant.DESCRIBE_TABLE:
            self._describe_table(arg)
        elif kind == assistant.COLUMNS:
            self._describe_columns()
        elif kind == assistant.SWITCH_DATABASE:
            self._switch_database(arg)
        elif kind == assistant.FOLLOW_UP:
            self._follow_up(arg, text)
        elif kind == assistant.MORE:
            self._more()
        elif kind == assistant.ADD_DATABASE:
            self.on_add_db(None)
        elif kind == assistant.REPEAT:
            a.announce(a.last_text or "I have not said anything yet.")
        elif kind == assistant.LAST_QUESTION:
            a.announce(f"You asked: {self.last_question}." if self.last_question else "You have not asked a question yet.")
        elif kind == assistant.READ_RESULTS:
            if self.outcome is None:
                a.announce("There are no results yet. Press Enter and ask a question.")
            else:
                a.announce(f"{self.outcome.description} {summary_sentence(self.outcome.result)}")
        elif kind == assistant.READ_ROW:
            count = self.outcome.result.row_count if self.outcome else 0
            self._read_row(count if arg == -1 else arg)
        elif kind == assistant.NEXT_ROW:
            self._step_row(+1)
        elif kind == assistant.PREVIOUS_ROW:
            self._step_row(-1)
        elif kind == assistant.READ_ALL:
            self.on_read_all(None)
        elif kind == assistant.ROW_COUNT:
            if self.outcome is None:
                a.announce("There are no results yet.")
            else:
                n = self.outcome.result.row_count
                more = " There are more than that; only the first ones are shown." if self.outcome.result.truncated else ""
                a.announce(f"{assistant.plural(n, 'row')}.{more}")
        elif kind == assistant.CANCEL:
            a.speaker.silence()
            self.status.SetValue("Stopped.")
        elif kind == assistant.CONFIRM_EXIT:
            self._pending_exit = True
            a.announce(assistant.CONFIRM_EXIT_TEXT)
        elif kind == assistant.EXIT:
            self._close_now()
        else:
            a.announce(f"I heard: {text}, but I do not know how to do that yet. Say help.")

    def _close_now(self):
        self.understood.SetValue("Close the program.")
        self.announcer.announce("Goodbye.")
        wx.CallLater(900, self.Close)

    def _describe_database(self, arg):
        engine, a = self.engine, self.announcer
        if arg:
            entry = engine.catalog.find(arg)
            if entry is None:
                a.announce(f"There is no database called {arg}. " +
                           assistant.databases_text(engine.catalog.names(), engine.current_name))
                return
            if entry.name != engine.current_name:
                self._select_in_list(entry.name)
                if not self._open_named(entry.name, announce=False):
                    return
        if engine.schema is None:
            a.announce(assistant.current_database_text(None, None))
            return
        self._last_kind = "database"
        a.announce(assistant.database_text(engine.current_name, engine.schema))

    def _switch_database(self, arg):
        engine, a = self.engine, self.announcer
        entry = engine.catalog.find(arg)
        if entry is None:
            a.announce(f"There is no database called {arg}. " +
                       assistant.databases_text(engine.catalog.names(), engine.current_name))
            return
        if entry.name == engine.current_name:
            a.announce(f"{entry.name} is already open.")
            return
        self._select_in_list(entry.name)
        if self._open_named(entry.name, announce=False):
            self.understood.SetValue(f"Switch to the {entry.name} database.")
            a.announce(f"Switched to {entry.name}. Tables: {', '.join(n.replace('_', ' ') for n in engine.schema.table_names)}. "
                       "Press Enter to ask a question.")

    def _describe_table(self, arg):
        engine, a = self.engine, self.announcer
        table = assistant.find_table(engine.schema, arg)
        if table is not None:
            self._last_table = table.name
            self._last_kind = "table"
            a.announce(assistant.table_text(table, engine.schema))
        elif engine.catalog.find(arg):
            self._describe_database(arg)
        elif engine.schema is None:
            a.announce(assistant.current_database_text(None, None))
        else:
            a.announce(f"I do not know a table called {arg}. " + assistant.tables_text(engine.current_name, engine.schema))

    def _describe_columns(self):
        schema = self.engine.schema
        if schema is None:
            self.announcer.announce(assistant.current_database_text(None, None))
            return
        table = schema.table(self._last_table) if self._last_table else None
        if table is None and len(schema.tables) == 1:
            table = next(iter(schema.tables.values()))
        if table is None:
            self.announcer.announce("Which table? " + assistant.tables_text(self.engine.current_name, schema))
            return
        self._describe_table(table.name)

    def _follow_up(self, arg, text):
        """'What about teams?': redo the last question for another table, or describe what was named."""
        engine = self.engine
        table = assistant.find_table(engine.schema, arg)
        if table is not None and self._last_kind == "results" and self.outcome and self.outcome.intent and self.last_question:
            old = self.outcome.intent.table
            question = self._swap_table(self.last_question, old, table.name)
            if question != self.last_question:
                self.heard.SetValue(question)
                self._ask_data(question, spoken=True)
                return
        if table is not None:
            self._describe_table(table.name)
        elif engine.catalog.find(arg):
            self._describe_database(arg)
        else:
            self._ask_data(arg, spoken=True)

    @staticmethod
    def _swap_table(question: str, old: str, new: str) -> str:
        new_spoken = new.replace("_", " ")
        for form in sorted({old.replace("_", " "), old, old.rstrip("s"), old.replace("_", " ").rstrip("s")}, key=len, reverse=True):
            changed = re.sub(r"\b" + re.escape(form) + r"\b", new_spoken, question, flags=re.IGNORECASE)
            if changed != question:
                return changed
        return question

    def _more(self):
        engine, a = self.engine, self.announcer
        if self._last_kind == "results" and self.outcome and self.outcome.result.row_count:
            result = self.outcome.result
            start = self._current_row() + 1
            if start >= result.row_count:
                a.announce("That was the last row. Press Enter to ask something else.")
                return
            end = min(start + 5, result.row_count)
            self.results.Select(end - 1)
            self.results.Focus(end - 1)
            text = " ".join(row_sentence(result, i) for i in range(start, end))
            if end < result.row_count:
                text += " Say more to continue."
            a.announce(text)
        elif self._last_kind == "table" and self._last_table and engine.schema and engine.schema.table(self._last_table):
            table = engine.schema.table(self._last_table)
            spoken = table.name.replace("_", " ")
            label = table.label_column
            ideas = [f"how many {spoken} are there", f"show the first 5 {spoken}"]
            if label:
                ideas.append(f"{spoken} sorted by {label.replace('_', ' ')}")
            a.announce(f"You can ask about {spoken} like this: " + "; or ".join(ideas) + ".")
        else:
            a.announce(assistant.examples_text(engine.current_name, engine.schema))

    # Results by voice and keyboard

    def _current_row(self) -> int:
        index = self.results.GetFirstSelected()
        return index if index >= 0 else 0

    def _read_row(self, number):
        if not self.outcome or not self.outcome.result.row_count:
            self.announcer.announce("There are no results yet.")
            return
        count = self.outcome.result.row_count
        if not number or number < 1:
            self.announcer.announce(f"Say a row number from 1 to {count}.")
            return
        if number > count:
            self.announcer.announce(f"There {'is' if count == 1 else 'are'} only {count} {'row' if count == 1 else 'rows'}.")
            return
        self.results.Select(number - 1)
        self.results.Focus(number - 1)
        self.announcer.announce(row_sentence(self.outcome.result, number - 1))

    def _step_row(self, step: int):
        if not self.outcome or not self.outcome.result.row_count:
            self.announcer.announce("There are no results yet.")
            return
        target = self._current_row() + step
        if target < 0:
            self.announcer.announce("This is the first row. " + row_sentence(self.outcome.result, 0))
            return
        if target >= self.outcome.result.row_count:
            self.announcer.announce("That was the last row. Press Enter to ask something else.")
            return
        self._read_row(target + 1)

    def on_read_row(self, event):
        self._read_row(self._current_row() + 1)

    def on_read_all(self, event):
        if not self.outcome or not self.outcome.result.row_count:
            self.announcer.announce("There are no results yet.")
            return
        result = self.outcome.result
        shown = min(result.row_count, READ_ALL_LIMIT)
        text = " ".join(row_sentence(result, i) for i in range(shown))
        if result.row_count > shown:
            text += f" That is the first {shown} of {result.row_count}. Say read row and a number for the others."
        self.announcer.announce(text)

    # Typing fallback, help, close

    def on_type(self, event):
        if self._state in (LISTENING, RUNNING):
            self.announcer.announce("Please wait until the current question is finished.")
            return
        typed = ask_typed(self, self.engine.settings.typed_sql_enabled)
        if typed is None:
            return
        text, use_sql = typed
        self.heard.SetValue(text)
        self.handle_text(text, spoken=False, use_sql=use_sql)

    def on_what_to_say(self, event):
        self.announcer.announce(assistant.help_text(self.engine.current_name, self.engine.schema))

    def on_shortcuts(self, event):
        self.announcer.announce(SHORTCUTS)
        wx.MessageBox(SHORTCUTS, "Keyboard shortcuts", wx.OK | wx.ICON_INFORMATION, self)

    def on_about(self, event):
        wx.MessageBox(f"{APP_TITLE} {__version__}. Ask questions about local SQLite databases by voice. "
                      "Read-only by design. Speech recognition runs on this computer; nothing is sent anywhere.",
                      "About", wx.OK | wx.ICON_INFORMATION, self)

    def on_close(self, event):
        self._stop_listening.set()
        self.engine.cancel()
        self.engine.close()
        event.Skip()
