"""Download and unpack the Vosk speech model (decision D9: the large English model, about 1.8 gigabytes).

This is the only file in the project allowed to use the network (CLAUDE.md). It is called by
tools/install.py and can also be run on its own:  python tools/download_model.py

The model goes to the user's local application data folder (AppData Local, Voice Database Query, models),
never into the repository. A partial download is resumed on the next run.
"""

import os
import shutil
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

MODEL_NAME = "vosk-model-en-us-0.22"
MODEL_URL = "https://alphacephei.com/vosk/models/" + MODEL_NAME + ".zip"
APPROXIMATE_SIZE = "1.8 gigabytes"
CHUNK = 1024 * 1024


def models_dir() -> Path:
    """Same place voicedbquery.config.paths.models_dir uses, without importing the package
    (this script runs with the system Python before the environment exists)."""
    override = os.environ.get("VDQ_HOME")
    if override:
        return Path(override).expanduser() / "local" / "models"
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
    return base / "Voice Database Query" / "models"


def model_installed(folder: "Path | None" = None) -> bool:
    folder = folder or models_dir() / MODEL_NAME
    return (folder / "conf").is_dir() and (folder / "am").is_dir()


def download(target_zip: Path, report, url: str = MODEL_URL) -> None:
    """Download url to target_zip, resuming a .part file if one exists. report(fraction) is called as bytes arrive."""
    part = target_zip.with_suffix(".zip.part")
    part.parent.mkdir(parents=True, exist_ok=True)
    have = part.stat().st_size if part.exists() else 0
    request = urllib.request.Request(url, headers={"User-Agent": "VoiceDatabaseQuery-installer"})
    if have:
        request.add_header("Range", f"bytes={have}-")
    try:
        response = urllib.request.urlopen(request, timeout=60)
    except urllib.error.HTTPError as exc:
        if exc.code == 416 and have:       # the part file is already complete
            part.rename(target_zip)
            report(1.0)
            return
        raise
    with response:
        if response.status == 206 and have:
            mode, done = "ab", have
            total = have + int(response.headers.get("Content-Length") or 0)
        else:
            mode, done = "wb", 0
            total = int(response.headers.get("Content-Length") or 0)
        with open(part, mode) as out:
            while True:
                block = response.read(CHUNK)
                if not block:
                    break
                out.write(block)
                done += len(block)
                if total:
                    report(min(done / total, 0.999))
    if total and part.stat().st_size != total:
        raise OSError(f"The download stopped early: {part.stat().st_size} of {total} bytes. Run the installer again to resume.")
    part.replace(target_zip)
    report(1.0)


def extract(zip_path: Path, destination: Path, report) -> Path:
    """Unpack the zip into destination. The zip holds one top folder named MODEL_NAME. report(fraction) per file."""
    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()
        top = names[0].split("/")[0] if names else MODEL_NAME
        for name in names:
            if ".." in Path(name).parts or Path(name).is_absolute():
                raise OSError("The model archive contains an unsafe path; refusing to unpack it.")
        tmp = destination / (top + ".unpacking")
        if tmp.exists():
            shutil.rmtree(tmp)
        for i, member in enumerate(archive.infolist(), start=1):
            archive.extract(member, tmp)
            report(i / len(names))
    final = destination / top
    if final.exists():
        shutil.rmtree(final)
    (tmp / top).rename(final)
    tmp.rmdir()
    return final


def install_model(report=lambda fraction: None, say=print) -> Path:
    """Download and unpack if needed. report(fraction) covers download then extraction, 0 to 1."""
    folder = models_dir() / MODEL_NAME
    if model_installed(folder):
        say("The speech model is already installed.")
        report(1.0)
        return folder
    zip_path = models_dir() / (MODEL_NAME + ".zip")
    if not zip_path.exists():
        say(f"Downloading the speech model, about {APPROXIMATE_SIZE}. This is the longest step.")
        download(zip_path, lambda f: report(0.85 * f))
    say("Unpacking the speech model.")
    extract(zip_path, models_dir(), lambda f: report(0.85 + 0.15 * f))
    zip_path.unlink(missing_ok=True)
    if not model_installed(folder):
        raise OSError("The model unpacked, but its folders are not where expected.")
    return folder


def main() -> int:
    last = [0]

    def report(fraction):
        pct = int(fraction * 100)
        for mark in range(last[0] + 10, pct + 1, 10):
            print(f"{mark} percent complete.", flush=True)
            last[0] = mark

    try:
        folder = install_model(report)
    except Exception as exc:  # noqa: BLE001
        print(f"The model download failed: {exc}", flush=True)
        return 1
    print(f"The speech model is installed in {folder}.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
