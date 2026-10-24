"""Listening beeps (decision D20), sine waves built in memory and played through the Windows sound system.

- Start beep: one B, played when Enter is pressed, before the microphone opens, so it is never recorded.
- Heard beep: the same B, then A flat one octave higher (A flat 6), held a little longer than the B.
  Played after the microphone closes and before any speech, to confirm the question was heard.

Pitch: B5, 987.77 hertz, the octave nearest the 1000 hertz tone used to bleep out words on air.
A flat 6 is 1661.22 hertz. Lengths were halved on 24 October 2026 at Russell's request. Each beep fades in and out over 8 milliseconds so it does not click.

Only the standard library is used (math, struct, wave, winsound). Nothing is written to disk.
"""

import io
import logging
import math
import struct
import sys
import wave

log = logging.getLogger(__name__)

SAMPLE_RATE = 44100
B5 = 987.77
A_FLAT_6 = 1661.22
VOLUME = 0.45            # of full scale; loud enough over a screen reader, not harsh
FADE_SECONDS = 0.008

START_BEEP = ((B5, 0.125),)                                   # twice as fast as the first version
HEARD_BEEP = ((B5, 0.09), (None, 0.03), (A_FLAT_6, 0.12))     # None is the silence between; A flat a tad slower


def samples(frequency: "float | None", seconds: float, rate: int = SAMPLE_RATE) -> list:
    """16-bit sample values for one sine tone, or silence when frequency is None."""
    count = int(rate * seconds)
    if frequency is None:
        return [0] * count
    fade = max(1, int(rate * FADE_SECONDS))
    peak = VOLUME * 32767
    out = []
    for i in range(count):
        envelope = min(1.0, i / fade, (count - 1 - i) / fade)
        out.append(int(peak * envelope * math.sin(2 * math.pi * frequency * i / rate)))
    return out


def wav_bytes(pattern, rate: int = SAMPLE_RATE) -> bytes:
    """A complete mono 16-bit WAV file, in memory, for a pattern of (frequency or None, seconds)."""
    values = []
    for frequency, seconds in pattern:
        values.extend(samples(frequency, seconds, rate))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack("<" + "h" * len(values), *values))
    return buffer.getvalue()


_cache = {}


def _sound(name: str, pattern) -> bytes:
    if name not in _cache:
        _cache[name] = wav_bytes(pattern)
    return _cache[name]


def play(data: bytes) -> None:
    """Play WAV bytes and return when finished. Call from a worker thread, never the interface thread.
    Never raises: a missing sound device must not stop a question."""
    if sys.platform != "win32":
        return
    try:
        import winsound

        winsound.PlaySound(data, winsound.SND_MEMORY | winsound.SND_NODEFAULT)
    except Exception:  # noqa: BLE001
        log.debug("Playing a beep failed", exc_info=True)


def play_start() -> None:
    play(_sound("start", START_BEEP))


def play_heard() -> None:
    play(_sound("heard", HEARD_BEEP))
