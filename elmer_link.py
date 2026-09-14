"""ELMER, from TowerWitch: the position it lends.

ELMER and TowerWitch are two programs on one bench. ELMER's dashboard has
a button that starts TowerWitch; this is what TowerWitch asks of ELMER in
return - a position, when there is no gpsd on the machine (a laptop,
Windows): ELMER's fix from a receiver or a phone, or the QTH typed into
it, offered as such.

There is no button the other way. One was tried: it opened a second copy
of ELMER's page beside the one already on the screen, which is worse than
no button. Getting back to ELMER is closing this window.

Nothing here reaches past this machine: ELMER on another unit is that
unit's business.
"""
import json
import os
import urllib.request
from pathlib import Path

URL = os.environ.get("ELMER_URL", "http://127.0.0.1:5000/")


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


def position(timeout=2.0):
    """ELMER's position, as its /api/gps answers it: `located` with lat and
    lon when it has a fix from a receiver or a phone, otherwise `qth` - the
    place typed into it - when it has one. None when ELMER is not there."""
    try:
        with urllib.request.urlopen(URL + "api/gps", timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
