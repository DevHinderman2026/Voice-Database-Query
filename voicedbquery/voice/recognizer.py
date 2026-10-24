"""Offline speech to text through Vosk.

The model (about 1.8 gigabytes for the large English model, decision D9) takes several seconds to
load, so the interface loads it in a background thread at startup and asks `ready` before listening.
Audio comes from voicedbquery.voice.audio_input and is never written to disk.
"""

import json
import logging
import queue
import time
from pathlib import Path

log = logging.getLogger(__name__)

MODEL_FOLDER_PREFIX = "vosk-model"
SAMPLE_RATE = 16000


class ModelMissing(Exception):
    """No speech model folder was found. The message is fit to be spoken."""


class RecognitionError(Exception):
    """Vosk itself failed. The message is fit to be spoken."""


def find_model(models_dir: Path) -> "Path | None":
    """The first folder under models_dir that looks like a Vosk model (has an am and a conf subfolder)."""
    if not models_dir.is_dir():
        return None
    for folder in sorted(models_dir.iterdir()):
        if folder.is_dir() and folder.name.startswith(MODEL_FOLDER_PREFIX) and (folder / "conf").is_dir():
            return folder
    return None


class Recognizer:
    def __init__(self, model_dir: "Path | None"):
        self.model_dir = model_dir
        self._model = None
        self.load_error: "str | None" = None

    @property
    def ready(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        """Load the model. Slow; call from a background thread. Sets load_error instead of raising."""
        if self.model_dir is None:
            self.load_error = ("The speech model is not installed. Run Install or Update Voice Database Query "
                               "to download it.")
            return
        try:
            import vosk
        except Exception as exc:  # noqa: BLE001
            log.exception("vosk import failed")
            self.load_error = "The speech package is not installed. Run Install or Update Voice Database Query."
            return
        try:
            vosk.SetLogLevel(-1)
            started = time.monotonic()
            self._model = vosk.Model(str(self.model_dir))
            log.info("Loaded speech model %s in %.1f seconds", self.model_dir.name, time.monotonic() - started)
        except Exception as exc:  # noqa: BLE001
            log.exception("Loading the speech model failed")
            self.load_error = f"The speech model could not be loaded: {exc}"

    def listen(self, microphone, stop_event, max_seconds: float = 12.0, silence_start_seconds: float = 6.0,
               on_partial=None) -> str:
        """Read audio from `microphone` until the speaker pauses, `stop_event` is set, or time runs out.

        Returns the transcript, which may be empty if nothing was heard. `on_partial(text)` is called
        with the words recognised so far, if given.
        """
        if self._model is None:
            raise ModelMissing(self.load_error or "The speech model is not loaded yet.")
        import vosk

        try:
            rec = vosk.KaldiRecognizer(self._model, SAMPLE_RATE)
        except Exception as exc:  # noqa: BLE001
            raise RecognitionError(f"Speech recognition could not start: {exc}") from exc
        started = time.monotonic()
        heard_words = False
        while not stop_event.is_set():
            now = time.monotonic()
            if now - started > max_seconds:
                break
            if not heard_words and now - started > silence_start_seconds:
                return ""
            try:
                chunk = microphone.read(timeout=0.5)
            except queue.Empty:
                continue
            if rec.AcceptWaveform(chunk):
                # Vosk decided the speaker paused: a complete utterance
                text = _text(rec.Result(), "text")
                if text:
                    return text
                continue
            partial = _text(rec.PartialResult(), "partial")
            if partial:
                heard_words = True
                if on_partial is not None:
                    on_partial(partial)
        return _text(rec.FinalResult(), "text")


def _text(payload: str, key: str) -> str:
    try:
        return (json.loads(payload).get(key) or "").strip()
    except (ValueError, AttributeError):
        return ""
