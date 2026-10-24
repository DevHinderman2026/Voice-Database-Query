"""Create the application and show the main window."""

import wx

from voicedbquery.config.catalog import Catalog
from voicedbquery.config.history import History
from voicedbquery.config.settings import Settings
from voicedbquery.engine import Engine
from voicedbquery.logging_setup import setup_logging
from voicedbquery.ui.main_window import MainWindow


def main() -> None:
    setup_logging()
    engine = Engine(Settings.load(), Catalog.load(), History.load())
    app = wx.App()
    MainWindow(engine).Show()
    app.MainLoop()
