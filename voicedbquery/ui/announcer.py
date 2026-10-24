"""Announce text to the screen reader and mirror it in the Status box.

Speech goes through voicedbquery.speech (ported from Musician Forge): NVDA, then JAWS, then Narrator
through UI Automation, then optionally the Windows voice when no screen reader is running.
The Status box always gets the text too, so it can be re-read and reaches a braille display.
"""

import wx

from voicedbquery.speech import Speaker


class Announcer:
    def __init__(self, status_ctrl, settings, hwnd_getter):
        self.status = status_ctrl
        self.settings = settings
        self.speaker = Speaker(hwnd_getter=hwnd_getter,
                               allow_sapi=settings.speech_without_screen_reader,
                               call_on_main=wx.CallAfter)
        self.last_text = ""   # for "repeat"

    def announce(self, text: str, interrupt: bool = True) -> None:
        self.last_text = text
        self.status.SetValue(text)
        if self.settings.speech_output:
            # spoken: "full name", not "full underline name"; the Status box keeps the exact names
            self.speaker.speak(text.replace("_", " "), interrupt)

    def output_name(self) -> str:
        return self.speaker.describe()
