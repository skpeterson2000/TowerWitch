"""RAVEN, from TowerWitch: a frequency handed to the receiver.

TowerWitch knows what is on the air near the station; RAVEN is the radio
that can listen to it. This is the hand-off between them: a repeater or a
weather channel picked from a table lands on RAVEN's dial, or in its
memory list, without anybody typing the frequency twice.

RAVEN's console at http://127.0.0.1:7283 takes a POST /api/tune. If its
audio is running the retune is immediate; if nobody is listening yet the
console picks the frequency up the moment it is. Either way TowerWitch
does not open the console: the lesson of the ELMER button was that a
program opening another program's page puts a second copy of it on the
screen, and the operator is better placed than we are to know whether
RAVEN's window is already up.

RAVEN normally runs on the machine with the HackRF, which is usually this
one. When it is on a Pi across the bench, RAVEN_URL says where.
"""
import json
import os
import urllib.error
import urllib.request

URL = os.environ.get("RAVEN_URL", "http://127.0.0.1:7283/")

# TowerWitch's mode column, in its own words, to the demodulator RAVEN names.
# Sideband without a side named goes upper above 10 MHz and lower below, the
# convention RAVEN's SSB detector follows itself.
MODES = {"FM": "nfm", "NFM": "nfm", "WFM": "wfm", "AM": "am", "USB": "usb", "LSB": "lsb"}


def mode_for(text, mhz=None):
    """RAVEN's mode name for a table's mode cell, nfm when in doubt."""
    words = str(text or "").upper().replace("/", " ").split()
    for word in words:
        if word in MODES:
            return MODES[word]
    if "SSB" in words or "CW" in words:
        return "usb" if (mhz or 0) >= 10.0 else "lsb"
    return "nfm"


def megahertz(text):
    """The number out of a cell like '147.225 MHz' or '162.550', or None.
    A cell in plain hertz - a tone - is not a frequency to tune to."""
    words = str(text or "").replace("/", " ").split()
    if any(w.lower() == "hz" for w in words):
        return None
    for word in words:
        try:
            value = float(word)
        except ValueError:
            continue
        if 1.0 <= value <= 6000.0:
            return value
    return None


def _post(path, body, timeout):
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(URL + path, data=data, method="POST",
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8")), ""
    except urllib.error.HTTPError as exc:
        try:
            got = json.loads(exc.read().decode("utf-8"))
            return None, str(got.get("reason") or exc)
        except (ValueError, OSError):
            return None, str(exc)
    except (OSError, ValueError) as exc:
        return None, "RAVEN is not answering at %s (%s)" % (URL, exc)


def answering(timeout=0.8):
    """Whether a RAVEN is answering where we expect one."""
    try:
        with urllib.request.urlopen(URL + "api/health", timeout=timeout):
            return True
    except Exception:
        return False


def tune(mhz, mode="nfm", timeout=2.0):
    """Put a frequency on RAVEN's dial. Returns (message, reason): the
    message is what to tell the operator when it worked, the reason is
    why it did not, and one of them is empty."""
    got, reason = _post("api/tune", {"freq_mhz": float(mhz), "mode": mode}, timeout)
    if reason:
        return "", reason
    if got.get("applied") == "live":
        return "RAVEN is on %.4f MHz %s" % (float(mhz), mode.upper()), ""
    return "RAVEN will take %.4f MHz %s when its console starts listening" % (float(mhz), mode.upper()), ""


def remember(name, mhz, mode="nfm", timeout=2.0):
    """Add a channel to RAVEN's memory list. Returns (message, reason)."""
    got, reason = _post("api/memories", {"name": str(name or "")[:40], "mhz": float(mhz), "mode": mode}, timeout)
    if reason:
        return "", reason
    item = got.get("memory") or {}
    return "%s is in RAVEN's memories at %.4f MHz" % (item.get("name") or name, float(mhz)), ""
