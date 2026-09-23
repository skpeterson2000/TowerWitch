"""frequency_store.py - where a county's frequencies live once imported.

The third kind of RadioReference export, and the odd one out. The other
two describe one trunked system: armer_state_store.py keeps its towers,
talkgroup_store.py keeps what is said on them. This one describes a
*place* - everything audible in one county, ham repeaters and airport
weather and the school buses together, each row carrying the Tag that
says which of those it is.

Kept by county, for the same reason talkgroups are kept by system: drive
an hour north and it is a different file describing different air, and
neither should overwrite the other. A receiver in the car wants whichever
county it is standing in, and wants the other one still there when it
comes home.

The rows tagged TRS are a county's view of a trunked system that reaches
it - the same ARMER frequencies trs_sites describes as sites. They are
kept rather than dropped: they are how you confirm a site is audible from
here, which the site list alone cannot tell you.

JSON shape (data/county_frequencies.json):
  {
    "counties": {
      "1327": {
        "county": "1327",
        "source": "ctid_1327_1790122872.csv",
        "imported_ts": 1750000000.0,
        "count": 90,
        "frequencies": [
          {"output_hz": 145130000, "input_hz": 144530000,
           "callsign": "W0UJ", "agency": "Amateur Radio",
           "description": "Brainerd ARC - VHF", "alpha_tag": "W0UJ VHF BRD",
           "tone_out": {...}, "tone_in": {...},
           "mode": "FM", "station_class": "RM", "tag": "Ham"},
          ...
        ]
      }
    },
    "meta": {"version": 1}
  }

Writing is atomic - a temporary file beside the real one, then a rename -
for the same reason as the other two: a Pi in a vehicle loses power mid
write eventually, and half a JSON file is worse than yesterday's whole
one.
"""

import json
import os
import tempfile
import time

VERSION = 1


def _empty():
    return {"counties": {}, "meta": {"version": VERSION}}


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
    if not isinstance(data, dict) or "counties" not in data:
        return _empty()
    data.setdefault("meta", {"version": VERSION})
    return data


def save(json_path, county, records, source=None):
    """Put one county's frequencies in, leaving the other counties alone.

    Re-importing a county replaces it outright rather than merging: the
    export is the whole truth about that county on the day it was
    downloaded, and a channel that has been retired should go when the
    new file does not list it.

    Returns the state as written.
    """
    county = str(county or "unknown")
    state = load(json_path)
    state["counties"][county] = {
        "county": county,
        "source": os.path.basename(source) if source else None,
        "imported_ts": time.time(),
        "count": len(records),
        "frequencies": list(records),
    }
    _atomic_write(json_path, state)
    return state


def forget(json_path, county):
    """Take one county out. Returns whether there was one to take out."""
    state = load(json_path)
    if str(county) not in state["counties"]:
        return False
    del state["counties"][str(county)]
    _atomic_write(json_path, state)
    return True


def counties(json_path):
    """Which counties have been imported, and what came in with each."""
    state = load(json_path)
    return [{"county": c, "count": entry.get("count", 0),
             "source": entry.get("source"),
             "imported_ts": entry.get("imported_ts")}
            for c, entry in sorted(state["counties"].items())]


def frequencies(json_path, county=None, tag=None):
    """Every frequency held, or one county's, or one tag's within that.

    `tag` is matched without regard to case, because the column is typed
    by hand upstream and "Ham" and "ham" are the same air. Passing a tag
    nobody uses returns nothing rather than everything, which is the
    answer that fails safe on a screen.
    """
    state = load(json_path)
    if county is None:
        entries = state["counties"].values()
    else:
        entry = state["counties"].get(str(county))
        entries = [entry] if entry else []
    out = []
    for entry in entries:
        for record in entry.get("frequencies", []):
            if tag is None or (record.get("tag") or "").lower() == tag.lower():
                out.append(record)
    return out


def tags(json_path, county=None):
    """Which tags are present, and how many rows carry each.

    What the Import button reports and what a routing decision is made
    from - Ham goes to the amateur tabs, and the rest of them are a
    question still open.
    """
    counted = {}
    for record in frequencies(json_path, county):
        name = (record.get("tag") or "").strip() or "(none)"
        counted[name] = counted.get(name, 0) + 1
    return dict(sorted(counted.items(), key=lambda kv: (-kv[1], kv[0])))


def _atomic_write(json_path, data):
    """Write beside the file, then rename over it."""
    folder = os.path.dirname(os.path.abspath(json_path))
    os.makedirs(folder, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=folder, prefix=".county-",
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
