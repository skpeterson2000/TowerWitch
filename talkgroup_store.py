"""talkgroup_store.py - where a system's talkgroups live once imported.

armer_state_store.py is the system of record for the towers. This is the
same idea for the other half of a RadioReference export: what is actually
said on them. A talkgroup is the number a radio is told to listen to, the
short tag a screen has room for, what it is for, whose it is, and whether
it is encrypted - which is the one that decides whether pointing a
receiver at it is worth anything at all.

Kept by system, because a vehicle that crosses a county line is on a
different system and the numbers mean different things there. The file
holds as many as have been imported and none of them tread on each other.

**A list, not a map keyed by number.** A RadioReference export really does
carry the same talkgroup twice - 2305 on ARMER is both "West EMRCC" and
"M Health Fairview North" - and a map would silently keep whichever came
last. Both are kept, in the order they were exported, and a lookup says
how many it found.

JSON shape (data/talkgroups.json):
  {
    "systems": {
      "3508": {
        "system": "3508",
        "source": "trs_tg_3508.csv",
        "imported_ts": 1750000000.0,
        "count": 1462,
        "talkgroups": [
          {"decimal": 2, "hex": "002", "alpha_tag": "SW IA MA 1",
           "description": "Interagency Mutual Aid 1",
           "tag": "Interop", "agency": "Statewide Interoperability",
           "mode": "D", "encrypted": false},
          ...
        ]
      }
    },
    "meta": {"version": 1}
  }

Writing is atomic - a temporary file beside the real one, then a rename -
because a vehicle loses power mid-write eventually, and a half-written
JSON file is worse than an old one.
"""

import json
import os
import tempfile
import time

VERSION = 1


def _empty():
    return {"systems": {}, "meta": {"version": VERSION}}


def load(json_path):
    """What is on disk, or an empty state. Never raises.

    A file that is missing, truncated or not JSON at all reads as empty,
    which is the honest answer and lets the caller offer an import rather
    than fall over on somebody's half-written file.
    """
    try:
        with open(json_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return _empty()
    if not isinstance(data, dict) or "systems" not in data:
        return _empty()
    data.setdefault("meta", {"version": VERSION})
    return data


def save(json_path, system, records, source=None):
    """Put one system's talkgroups in, leaving the other systems alone.

    Re-importing a system replaces it outright rather than merging: the
    export is the whole truth about that system on the day it was
    downloaded, and a talkgroup that has been retired should go when the
    new file does not list it.

    Returns the state as written.
    """
    system = str(system or "unknown")
    state = load(json_path)
    state["systems"][system] = {
        "system": system,
        "source": os.path.basename(source) if source else None,
        "imported_ts": time.time(),
        "count": len(records),
        "talkgroups": list(records),
    }
    _atomic_write(json_path, state)
    return state


def forget(json_path, system):
    """Take one system out. Returns whether there was one to take out."""
    state = load(json_path)
    if str(system) not in state["systems"]:
        return False
    del state["systems"][str(system)]
    _atomic_write(json_path, state)
    return True


def systems(json_path):
    """Which systems have talkgroups here, as {id: count}."""
    return {sid: entry.get("count", len(entry.get("talkgroups", [])))
            for sid, entry in load(json_path).get("systems", {}).items()}


def talkgroups(json_path, system=None):
    """Every talkgroup, or one system's. In the order they were exported."""
    state = load(json_path)
    if system is not None:
        entry = state["systems"].get(str(system)) or {}
        return list(entry.get("talkgroups", []))
    out = []
    for entry in state["systems"].values():
        out.extend(entry.get("talkgroups", []))
    return out


def find(json_path, decimal, system=None):
    """Every talkgroup with this number - see the note about duplicates."""
    try:
        decimal = int(decimal)
    except (TypeError, ValueError):
        return []
    return [t for t in talkgroups(json_path, system)
            if t.get("decimal") == decimal]


def _atomic_write(json_path, data):
    """Write beside the file, then rename over it.

    A vehicle loses power in the middle of a write eventually, and half a
    JSON file is worse than yesterday's whole one.
    """
    folder = os.path.dirname(os.path.abspath(json_path))
    os.makedirs(folder, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=folder, prefix=".talkgroups-",
                                         suffix=".json")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            json.dump(data, out, indent=1)
        os.replace(temporary, json_path)
    except OSError:
        try:
            os.unlink(temporary)
        except OSError:
            pass                       # the write already failed; say nothing more
        raise
