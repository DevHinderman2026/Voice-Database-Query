"""Install or update Voice Database Query, announcing progress at every 10 percent (decision D18).

Run by "Install or Update Voice Database Query.bat" with the system Python. Uses only the standard library,
because the private environment does not exist yet when this starts.

Steps and their share of the progress:
  1. Private Python environment              0 to 10 percent
  2. pip itself                             10 to 15 percent
  3. Packages from requirements.txt         15 to 40 percent, in equal parts
  4. Speech model download and unpacking    40 to 95 percent (skipped quickly if already installed)
  5. Checks                                 95 to 100 percent
"""

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import download_model  # noqa: E402  (tools/download_model.py, the only file allowed to use the network)


class Progress:
    """Prints "N percent complete." once for every 10 percent mark passed, in order, never twice."""

    def __init__(self, say=print):
        self.say = say
        self.announced = 0
        self.fraction = 0.0

    def set(self, fraction: float) -> None:
        self.fraction = max(self.fraction, min(fraction, 1.0))
        pct = int(round(self.fraction * 100))
        for mark in range(self.announced + 10, pct + 1, 10):
            self.say(f"{mark} percent complete.")
            self.announced = mark

    def span(self, start: float, end: float):
        """A reporter for a sub-step that runs from `start` to `end` of the whole."""
        return lambda f: self.set(start + (end - start) * max(0.0, min(f, 1.0)))


def say(text: str) -> None:
    print(text, flush=True)


def venv_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "Voice Database Query" / "venv"


def venv_python(venv: Path) -> Path:
    return venv / ("Scripts" if sys.platform == "win32" else "bin") / ("python.exe" if sys.platform == "win32" else "python")


def run(args, what: str) -> None:
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip().splitlines()[-12:]
        raise RuntimeError(f"{what} failed.\n" + "\n".join(tail))


def requirement_lines(path: Path) -> list:
    lines = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            lines.append(line)
    return lines


def main() -> int:
    progress = Progress(say)
    say("Installing Voice Database Query. I will announce every 10 percent.")
    try:
        venv = venv_dir()
        py = venv_python(venv)
        if not py.exists():
            say("Creating a private Python environment.")
            run([sys.executable, "-m", "venv", str(venv)], "Creating the Python environment")
        progress.set(0.10)

        run([str(py), "-m", "pip", "install", "--upgrade", "--quiet", "pip"], "Updating pip")
        progress.set(0.15)

        packages = requirement_lines(ROOT / "requirements.txt")
        dev = ROOT / "requirements-dev.txt"       # only on the development branch, for the tests
        if dev.exists():
            packages += requirement_lines(dev)
        say(f"Installing {len(packages)} packages.")
        step = progress.span(0.15, 0.40)
        for i, package in enumerate(packages, start=1):
            run([str(py), "-m", "pip", "install", "--quiet", package], f"Installing {package}")
            step(i / len(packages))

        download_model.install_model(progress.span(0.40, 0.95), say)

        say("Checking the installation.")
        run([str(py), "-c", "import wx, vosk, sounddevice, accessible_output2"], "Checking the packages")
        progress.set(1.0)
    except Exception as exc:  # noqa: BLE001
        say(f"The installation stopped at {int(progress.fraction * 100)} percent. {exc}")
        say("Run the installer again; a model download continues where it left off.")
        return 1
    say("Voice Database Query is installed and ready. Run Start Voice Database Query.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
