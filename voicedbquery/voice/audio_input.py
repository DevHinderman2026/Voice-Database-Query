"""Microphone capture through sounddevice.

Produces 16 kilohertz, mono, 16-bit chunks of raw audio on a queue. The stream is open only while
a Microphone is being used as a context manager, so the microphone is never left on. Nothing is
written to disk.

sounddevice is imported inside the functions so this module can be imported, and the rest of the
program tested, on a machine without the package or without a sound card.
"""

import logging
import queue

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000     # what the Vosk English models expect
CHANNELS = 1
DTYPE = "int16"


class MicrophoneError(Exception):
    """No usable microphone, or the audio package is missing. The message is fit to be spoken."""


def default_microphone_name() -> "str | None":
    """The name of the default input device, or None when there is none."""
    try:
        import sounddevice as sd
    except Exception:  # noqa: BLE001 - missing package or missing PortAudio library
        return None
    try:
        index = sd.default.device[0]
        if index is None or index < 0:
            return None
        info = sd.query_devices(index)
        if int(info.get("max_input_channels", 0)) < 1:
            return None
        return str(info.get("name", "microphone"))
    except Exception:  # noqa: BLE001
        log.debug("Could not query the default microphone", exc_info=True)
        return None


class Microphone:
    """Use with `with Microphone() as mic:` then call mic.read() repeatedly."""

    def __init__(self, sample_rate: int = SAMPLE_RATE, block_seconds: float = 0.25):
        self.sample_rate = sample_rate
        self.block_size = int(sample_rate * block_seconds)
        self.chunks: "queue.Queue[bytes]" = queue.Queue()
        self._stream = None

    def __enter__(self):
        try:
            import sounddevice as sd
        except Exception as exc:  # noqa: BLE001
            raise MicrophoneError("The audio package is not installed. Run Install or Update Voice Database Query.") from exc

        def on_audio(indata, frames, time_info, status):
            if status:
                log.debug("Audio status: %s", status)
            self.chunks.put(bytes(indata))

        try:
            self._stream = sd.RawInputStream(samplerate=self.sample_rate, blocksize=self.block_size,
                                             dtype=DTYPE, channels=CHANNELS, callback=on_audio)
            self._stream.start()
        except Exception as exc:  # noqa: BLE001 - PortAudio reports many kinds of error
            self._stream = None
            raise MicrophoneError("I could not open a microphone. Check that one is plugged in and allowed "
                                  "in Windows privacy settings.") from exc
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:  # noqa: BLE001
                log.debug("Closing the microphone failed", exc_info=True)
            self._stream = None
        # drop any audio still queued; nothing is kept
        while not self.chunks.empty():
            try:
                self.chunks.get_nowait()
            except queue.Empty:
                break
        return False

    def read(self, timeout: float = 0.5) -> bytes:
        """The next chunk of audio. Raises queue.Empty if none arrives within timeout seconds."""
        return self.chunks.get(timeout=timeout)
