"""ELMER, from TowerWitch: the button to the other dashboard.

ELMER and TowerWitch are two programs on one bench. ELMER has a button to
TowerWitch on its dashboard, greyed when TowerWitch is not installed; this
is the same button the other way round. It finds ELMER beside TowerWitch
(or wherever ELMER_HOME says), tells whether one is already answering on
this machine, and on the press opens the browser to it - starting ELMER
first if it is installed but not running. Greyed, with the reason in the
tooltip, when there is nothing to open.

Nothing here reaches past this machine: ELMER on another unit is that
unit's dashboard to open.
"""
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

URL = os.environ.get("ELMER_URL", "http://127.0.0.1:5000/")
START_WAIT_S = 30.0


def find():
    """Where ELMER is installed, or None: ELMER_HOME, the usual folders in
    the home directory, or a folder beside this one."""
    named = os.environ.get("ELMER_HOME")
    here = Path(__file__).resolve().parent
    home = Path.home()
    candidates = [Path(named).expanduser()] if named else []
    candidates += [home / "elmer", home / "elmer-main", home / "elmer-main" / "elmer-1",
                   home / "ELMER", here.parent / "elmer", here.parent / "elmer-main",
                   here.parent / "ELMER"]
    for path in candidates:
        try:
            if (path / "elmer.py").is_file() and (path / "elmer" / "app.py").is_file():
                return path
        except OSError:
            continue
    return None


def answering(timeout=0.8):
    """Whether an ELMER is answering on this machine."""
    try:
        with urllib.request.urlopen(URL + "api/window", timeout=timeout):
            return True
    except Exception:
        return False


def status():
    path = find()
    return {"installed": path is not None, "path": str(path) if path else None,
            "running": answering()}


def _start(path):
    """Start ELMER from its folder, detached. Returns (ok, said)."""
    path = Path(path)
    if os.name == "nt":
        cmd = [str(path / "elmer.cmd")] if (path / "elmer.cmd").is_file() else [sys.executable, str(path / "elmer.py")]
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        kw = {"creationflags": flags}
    else:
        py = path / ".venv" / "bin" / "python"
        cmd = [str(py) if py.is_file() else sys.executable, str(path / "elmer.py")]
        kw = {"start_new_session": True}
    try:
        subprocess.Popen(cmd, cwd=str(path), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw)
    except OSError as exc:
        return False, f"could not start ELMER: {exc}"
    t0 = time.time()
    while time.time() - t0 < START_WAIT_S:
        if answering(0.5):
            return True, "ELMER started"
        time.sleep(0.5)
    return False, "ELMER was started but is not answering yet - try the button again in a moment"


def open_dashboard():
    """The press. Returns (ok, said)."""
    if answering():
        webbrowser.open(URL)
        return True, "opened ELMER"
    path = find()
    if path is None:
        return False, "ELMER is not on this machine"
    ok, said = _start(path)
    if ok:
        webbrowser.open(URL)
    return ok, said
