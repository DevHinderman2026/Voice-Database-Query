"""Typing fallback (decision D16): a small dialog for a typed question or SQL, reached with Control plus T.

Voice is the main path. This exists so the program stays usable when the microphone or the speech
model fails, and for the typed SQL mode chosen in decision O2.
"""

import wx


class TypeDialog(wx.Dialog):
    def __init__(self, parent, sql_enabled: bool):
        super().__init__(parent, title="Type a question", size=(560, 220))
        panel = wx.Panel(self)
        label = wx.StaticText(panel, label="&Question or SQL statement:")
        self.text = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER)
        self.sql_mode = wx.CheckBox(panel, label="&SQL mode (the text is a SELECT statement)")
        self.sql_mode.Enable(sql_enabled)
        buttons = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(label, 0, wx.ALL, 8)
        sizer.Add(self.text, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
        sizer.Add(self.sql_mode, 0, wx.ALL, 8)
        sizer.Add(buttons, 0, wx.ALIGN_RIGHT | wx.ALL, 8)
        panel.SetSizer(sizer)
        self.text.Bind(wx.EVT_TEXT_ENTER, lambda e: self.EndModal(wx.ID_OK))
        self.text.SetFocus()

    def result(self):
        return self.text.GetValue().strip(), self.sql_mode.GetValue()


def ask_typed(parent, sql_enabled: bool):
    """Return (text, use_sql) or None if cancelled or empty."""
    with TypeDialog(parent, sql_enabled) as dlg:
        if dlg.ShowModal() != wx.ID_OK:
            return None
        text, use_sql = dlg.result()
    return (text, use_sql) if text else None
