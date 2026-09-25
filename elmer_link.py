"""ELMER, from TowerWitch: the position it lends.

ELMER and TowerWitch are two programs on one bench. ELMER's dashboard has
a button that starts TowerWitch; this is what TowerWitch asks of ELMER in
return - a position, when there is no gpsd on the machine (a laptop,
Windows): ELMER's fix from a receiver or a phone, or the QTH typed into
it, offered as such.

There is no button the other way. One was tried: it opened a second copy
of ELMER's page beside the one already on the screen, which is worse than
no button. Getting back to ELMER is closing this window.

The ELMER on this machine is asked first, because it already ranks every
source it knows of - its receiver, a phone, TowerWitch's own broadcast,
another ELMER's announcement - and answers with the best. But a laptop
need not have an ELMER at all, and a house can have several: the one on
the Pi with the puck is the one that actually knows where the station
is. So this also listens for what every ELMER on the network says about
itself, on the port the ELMERs use between themselves, and when the local
one has nothing, takes a fix from any ELMER that has one of its own.
Nothing is configured; an ELMER is heard or it is not.
"""
import json
import os
import socket
import threading
import time
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


def local_position(timeout=2.0):
    """The position of the ELMER on this machine, as its /api/gps answers
    it: `located` with lat and lon when it has a fix from a receiver, a
    phone or a neighbour, otherwise `qth` - the place typed into it - when
    it has one. None when ELMER is not there."""
    try:
        with urllib.request.urlopen(URL + "api/gps", timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


# ------------------------------------------------- every ELMER on the network
# ELMERs say hello to each other every eight seconds on udp/12346, and a unit
# with a receiver puts its fix in the greeting. This is the same packet, read
# by TowerWitch. The magic word and the shape are ELMER's (elmer/discovery.py).
ANNOUNCE_PORT = 12346
MAGIC = "elmer-unit"
GONE_AFTER = 30.0        # three missed greetings and that ELMER has gone
# A fix an ELMER did not get from its own receiver or phone is not one to
# borrow: "elmer-peer" it borrowed from another ELMER (ELMER never announces
# those, but the rule is kept here too), and "towerwitch-net" it took from a
# TowerWitch's broadcast - possibly this one's, coming back round.
NOT_ITS_OWN = ("elmer-peer", "towerwitch-net", "towerwitch")


def parse_announcement(data, address):
    """One ELMER greeting as a record, or None if it is not one."""
    try:
        got = json.loads(data.decode("utf-8", "ignore"))
    except (ValueError, AttributeError):
        return None
    if not isinstance(got, dict) or got.get("elmer") != MAGIC or not got.get("unit"):
        return None
    peer = {"unit": str(got["unit"])[:40], "name": str(got.get("name") or got["unit"])[:60],
            "url": str(got.get("url") or "")[:120], "address": address, "heard_at": time.time(), "gps": None}
    gps = got.get("gps")
    if isinstance(gps, dict):
        try:
            lat, lon = float(gps["lat"]), float(gps["lon"])
        except (KeyError, TypeError, ValueError):
            lat = lon = None
        if lat is not None and -90 <= lat <= 90 and -180 <= lon <= 180:
            peer["gps"] = {"lat": lat, "lon": lon, "mode": gps.get("mode") or 2,
                           "source": str(gps.get("source") or "gps"), "age_s": float(gps.get("age_s") or 0.0)}
    return peer


class Neighbours:
    """The ELMERs heard on this network, and which of them knows where it is."""

    def __init__(self, port=ANNOUNCE_PORT):
        self.port = int(port)
        self.peers = {}
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.sock = None
        self.thread = None
        self.error = None

    def start(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # The ELMER on this machine holds the same port; both may listen.
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.settimeout(1.0)
            self.sock.bind(("", self.port))
        except OSError as exc:
            self.error = str(exc)
            return self
        self.thread = threading.Thread(target=self._run, daemon=True, name="elmer-neighbours")
        self.thread.start()
        return self

    def _run(self):
        while not self.stop.is_set():
            try:
                data, sender = self.sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            peer = parse_announcement(data, sender[0])
            if peer is not None:
                with self.lock:
                    self.peers[peer["unit"]] = peer

    def close(self):
        self.stop.set()
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass

    def current(self, now=None):
        now = time.time() if now is None else now
        with self.lock:
            return [dict(p) for p in self.peers.values() if now - p["heard_at"] <= GONE_AFTER]

    def with_fix(self, now=None):
        """The ELMER whose own receiver has the freshest fix, or None."""
        found = [p for p in self.current(now)
                 if p["gps"] and p["gps"]["source"] not in NOT_ITS_OWN]
        found.sort(key=lambda p: p["gps"]["age_s"] + (time.time() if now is None else now) - p["heard_at"])
        return found[0] if found else None


_neighbours = None
_lock = threading.Lock()


def listen(port=ANNOUNCE_PORT):
    """Start hearing the ELMERs on the network, once. Returns the Neighbours."""
    global _neighbours
    with _lock:
        if _neighbours is None:
            _neighbours = Neighbours(port).start()
        return _neighbours


def neighbours():
    return _neighbours


def position(timeout=2.0):
    """The suite's best idea of where the station is, in the shape of
    ELMER's /api/gps: the ELMER on this machine when it is located, else
    any ELMER on the network announcing a fix of its own, else whatever the
    local one had to say (its typed QTH, or its reasons), else None."""
    got = local_position(timeout)
    if got and got.get("located") and (got.get("source") or "") in NOT_ITS_OWN:
        # ELMER is located, but on a position it learned from a TowerWitch -
        # possibly this one's, coming back round. NOT_ITS_OWN was being
        # applied to what the other ELMERs announce and not to what the one
        # on this machine answers, which is the path that actually loops:
        # TowerWitch broadcasts its last known position, ELMER takes it as a
        # fix, TowerWitch asks ELMER and is handed its own answer back with
        # a grid on it. Seen in the field as EN34ix - the Minneapolis
        # default - on every screen in the house with a receiver in none.
        #
        # Refused, and put back as not located so no caller mistakes it for
        # one. The QTH travelling with it is untouched and is the answer.
        got = dict(got, located=False, refused=got.get("source"),
                   reason="that fix is a TowerWitch's own, come back round")
    if got and got.get("located"):
        return got
    peer = _neighbours.with_fix() if _neighbours is not None else None
    if peer is not None:
        gps = peer["gps"]
        words = "ELMER on %s at %s" % (peer["name"], peer["address"])
        return {"located": True, "lat": gps["lat"], "lon": gps["lon"], "mode": gps["mode"],
                "age_s": gps["age_s"], "source": "elmer-peer", "from": words, "url": peer["url"],
                "sleuth": {"words": words, "quality": "3D" if gps["mode"] == 3 else "2D",
                           "advice": None, "source": "elmer-peer"}}
    return got
