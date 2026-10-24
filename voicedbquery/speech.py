"""Spoken announcements through the screen reader you are using.

Ported from Musician Forge (its speech module, 23 Oct 2026) so both programs announce the same way,
including the fixes from its screen reader audit (braille messages for NVDA, notification handling for Narrator).

Order of preference, checked each time something is spoken (with a short
cache so it stays fast):

1. NVDA, through NV Access's controller client DLL.
2. JAWS, through its FreedomSci.JawsApi COM interface.
3. Narrator (or any screen reader that listens to UI Automation), through a
   UI Automation notification event raised on Voice Database Query's main window.
4. Optionally, the Windows SAPI voice when no screen reader is running.

Controls in Voice Database Query's windows are standard Windows controls, which every
screen reader reads on its own. This module is only for announcements such as
"Running" or "12 rows" that do not come from a focused control.
"""

import ctypes
import importlib.util
import logging
import os
import sys
import threading
import time

log = logging.getLogger("voicedbquery.speech")

NOTIFICATION_KIND_OTHER = 4
NOTIFICATION_PROCESSING_IMPORTANT_MOST_RECENT = 1
NOTIFICATION_PROCESSING_ALL = 2
NOTIFICATION_PROCESSING_MOST_RECENT = 3
SPI_GETSCREENREADER = 0x0046


class _Output:
    name = "none"

    def is_active(self):
        return False

    def speak(self, text, interrupt):
        raise NotImplementedError

    def silence(self):
        pass


class NvdaOutput(_Output):
    name = "NVDA"

    def __init__(self, dll_path):
        self.dll = ctypes.WinDLL(dll_path)
        self.dll.nvdaController_testIfRunning.restype = ctypes.c_ulong
        self.dll.nvdaController_speakText.argtypes = [ctypes.c_wchar_p]
        self.dll.nvdaController_speakText.restype = ctypes.c_ulong
        self.dll.nvdaController_cancelSpeech.restype = ctypes.c_ulong
        self.dll.nvdaController_brailleMessage.argtypes = [ctypes.c_wchar_p]
        self.dll.nvdaController_brailleMessage.restype = ctypes.c_ulong

    def is_active(self):
        return self.dll.nvdaController_testIfRunning() == 0

    def speak(self, text, interrupt):
        if interrupt:
            self.dll.nvdaController_cancelSpeech()
        spoken = self.dll.nvdaController_speakText(text) == 0
        try:
            # on a braille display too, as a message (screen reader audit E3, 23 Oct 2026): speakText alone
            # reached only the voice
            self.dll.nvdaController_brailleMessage(text)
        except Exception:  # noqa: BLE001 - braille is extra; speech has already gone
            log.debug("NVDA braille message failed", exc_info=True)
        return spoken

    def silence(self):
        self.dll.nvdaController_cancelSpeech()


class JawsOutput(_Output):
    name = "JAWS"

    def __init__(self):
        self._api = None

    def is_active(self):
        return bool(ctypes.windll.user32.FindWindowW("JFWUI2", None))

    def _connect(self):
        if self._api is None:
            import pythoncom  # from pywin32
            import win32com.client

            pythoncom.CoInitialize()
            self._api = win32com.client.Dispatch("FreedomSci.JawsApi")
        return self._api

    def speak(self, text, interrupt):
        try:
            return bool(self._connect().SayString(text, bool(interrupt)))
        except Exception:  # noqa: BLE001 - JAWS may have restarted
            self._api = None
            return bool(self._connect().SayString(text, bool(interrupt)))

    def silence(self):
        try:
            self._connect().StopSpeech()
        except Exception:  # noqa: BLE001
            pass


class UiaNotificationOutput(_Output):
    """Narrator and other UI Automation clients: raise a notification event."""

    name = "Narrator (UI Automation)"

    def __init__(self, hwnd_getter):
        self._hwnd_getter = hwnd_getter
        self._uia = ctypes.WinDLL("UIAutomationCore.dll")
        self._uia.UiaHostProviderFromHwnd.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
        self._uia.UiaHostProviderFromHwnd.restype = ctypes.c_long
        self._uia.UiaRaiseNotificationEvent.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                                                        ctypes.c_void_p, ctypes.c_void_p]
        self._uia.UiaRaiseNotificationEvent.restype = ctypes.c_long
        self._oleaut = ctypes.WinDLL("oleaut32.dll")
        self._oleaut.SysAllocString.argtypes = [ctypes.c_wchar_p]
        self._oleaut.SysAllocString.restype = ctypes.c_void_p
        self._oleaut.SysFreeString.argtypes = [ctypes.c_void_p]

    def is_active(self):
        flag = ctypes.c_int(0)
        ctypes.windll.user32.SystemParametersInfoW(SPI_GETSCREENREADER, 0, ctypes.byref(flag), 0)
        return bool(flag.value) and bool(self._hwnd_getter())

    def speak(self, text, interrupt):
        hwnd = self._hwnd_getter()
        if not hwnd:
            return False
        provider = ctypes.c_void_p()
        if self._uia.UiaHostProviderFromHwnd(hwnd, ctypes.byref(provider)) != 0 or not provider.value:
            return False
        display = self._oleaut.SysAllocString(text)
        activity = self._oleaut.SysAllocString("VoiceDatabaseQueryAnnouncement")
        try:
            # not interrupting: every one is read, in turn. MOST_RECENT (until 23 Oct 2026) let a newer notification
            # with the same activity replace one still waiting, and some screen readers treat it as "stop and say
            # this" (screen reader audit E1)
            processing = (NOTIFICATION_PROCESSING_IMPORTANT_MOST_RECENT if interrupt
                          else NOTIFICATION_PROCESSING_ALL)
            result = self._uia.UiaRaiseNotificationEvent(provider, NOTIFICATION_KIND_OTHER,
                                                         processing, display, activity)
            return result == 0
        finally:
            self._oleaut.SysFreeString(display)
            self._oleaut.SysFreeString(activity)
            _com_release(provider.value)


class SapiOutput(_Output):
    name = "Windows voice (SAPI)"

    def __init__(self):
        self._voice = None

    def is_active(self):
        return True

    def speak(self, text, interrupt):
        if self._voice is None:
            import pythoncom
            import win32com.client

            pythoncom.CoInitialize()
            self._voice = win32com.client.Dispatch("SAPI.SpVoice")
        flags = 1 | (2 if interrupt else 0)  # async, purge before speak
        self._voice.Speak(text, flags)
        return True

    def silence(self):
        if self._voice is not None:
            self._voice.Speak("", 1 | 2)


def _com_release(pointer_value):
    vtable = ctypes.cast(pointer_value, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtable[2])
    release(pointer_value)


def find_nvda_dll():
    """nvdaControllerClient DLL shipped inside the accessible_output2 package."""
    bits = "64" if sys.maxsize > 2 ** 32 else "32"
    spec = importlib.util.find_spec("accessible_output2")
    folders = list(spec.submodule_search_locations or []) if spec else []
    for folder in folders:
        candidate = os.path.join(folder, "lib", "nvdaControllerClient{}.dll".format(bits))
        if os.path.isfile(candidate):
            return candidate
    return None


class Speaker:
    """Chooses an output and speaks text. Safe to call from any thread."""

    CACHE_SECONDS = 2.0

    def __init__(self, hwnd_getter=None, outputs=None, allow_sapi=False, call_on_main=None):
        self._hwnd_getter = hwnd_getter or (lambda: None)
        self.allow_sapi = allow_sapi
        self.call_on_main = call_on_main  # e.g. wx.CallAfter, set by the user interface
        self._outputs = outputs if outputs is not None else self._build_outputs()
        self._active = None
        self._sapi = None            # one Windows voice for the whole run
        self._checked_at = -1e9
        self._lock = threading.Lock()
        self.last_text = ""
        self.enabled = True

    def _build_outputs(self):
        outputs = []
        if sys.platform != "win32":
            return outputs
        try:
            dll = find_nvda_dll()
            if dll:
                outputs.append(NvdaOutput(dll))
            else:
                log.warning("NVDA controller DLL not found (accessible_output2 missing?)")
        except Exception:  # noqa: BLE001
            log.exception("Could not set up NVDA speech")
        try:
            outputs.append(JawsOutput())
        except Exception:  # noqa: BLE001
            log.exception("Could not set up JAWS speech")
        try:
            outputs.append(UiaNotificationOutput(self._hwnd_getter))
        except Exception:  # noqa: BLE001
            log.exception("Could not set up UI Automation notifications")
        return outputs

    def set_window_getter(self, hwnd_getter):
        self._hwnd_getter = hwnd_getter
        for output in self._outputs:
            if isinstance(output, UiaNotificationOutput):
                output._hwnd_getter = hwnd_getter

    def active_output(self, refresh=False):
        now = time.monotonic()
        if not refresh and now - self._checked_at < self.CACHE_SECONDS:
            return self._active
        chosen = None
        for output in self._outputs:
            try:
                if output.is_active():
                    chosen = output
                    break
            except Exception:  # noqa: BLE001
                log.debug("Speech output %s check failed", output.name, exc_info=True)
        if chosen is None and self.allow_sapi and sys.platform == "win32":
            # the same voice every time: a new one every two seconds (before 9 Oct 2026) could speak over the one
            # before, since "stop what you are saying" only reaches the voice it is sent to
            if self._sapi is None:
                self._sapi = SapiOutput()
            chosen = self._sapi
        if (chosen.name if chosen else None) != (self._active.name if self._active else None):
            log.info("Speech output: %s", chosen.name if chosen else "none")
        self._active, self._checked_at = chosen, now
        return chosen

    def describe(self, refresh=True):
        """The output's name. refresh=False: the one chosen in the last two seconds, without asking each screen
        reader again (for the Status area, which is filled again after every key)."""
        output = self.active_output(refresh=refresh)
        return output.name if output else "none (no screen reader detected)"

    def speak(self, text, interrupt=True):
        """Speak `text`. Returns immediately; never raises."""
        if not text or not self.enabled:
            return
        self.last_text = text
        if self.call_on_main is not None and threading.current_thread() is not threading.main_thread():
            self.call_on_main(self._speak_now, text, interrupt)
        else:
            self._speak_now(text, interrupt)

    def _speak_now(self, text, interrupt):
        with self._lock:
            output = self.active_output()
            if output is None:
                return
            try:
                output.speak(text, interrupt)
            except Exception:  # noqa: BLE001
                log.exception("Speaking through %s failed", output.name)
                self._checked_at = -1e9  # look again next time

    def silence(self):
        output = self.active_output()
        if output is not None:
            try:
                output.silence()
            except Exception:  # noqa: BLE001
                log.debug("silence failed", exc_info=True)


speaker = Speaker()
