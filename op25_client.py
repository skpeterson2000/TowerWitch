"""
op25_client.py - background poller for a running op25 multi_rx HTTP terminal.

Polls every 250ms (matching op25's web UI refresh), parses trunk_update
messages, fires a callback with each new SystemState observation.

Modeled on op25's own sniffer_http.py reference implementation.

Usage from TowerWitch:
    from op25_client import Op25Client
    from armer_state_store import update_from_op25

    client = Op25Client(
        url=["http://localhost:8080/", "http://192.168.1.31:8080/"],
        on_update=lambda st: update_from_op25(json_path, st),
        on_status=lambda reachable, url: ...,   # button state
    )
    client.start()
    ...
    client.stop()

`url` may be one address or several: the first that answers is used until
it stops answering. While nothing answers the poll slows to `absent_poll_sec`
so an op25 that is not there costs a request every ten seconds, not four a
second, and the log hears about it once.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Adjacent:
    cc_freq_hz: int
    rfid: int
    stid: int
    uplink_hz: int = 0


@dataclass(frozen=True)
class Op25SystemState:
    nac: int
    wacn: int
    sysid: int
    rfid: int
    stid: int
    cc_freq_hz: int
    tx_freq_hz: int
    adjacents: tuple = field(default_factory=tuple)
    observed_at: float = field(default_factory=time.time)


class Op25Client(threading.Thread):
    # Misses in a row before a reachable op25 is called lost; one dropped
    # poll should not flip the button.
    LOST_AFTER = 3

    def __init__(
        self,
        url,
        on_update,
        poll_sec: float = 0.25,
        timeout_sec: float = 2.0,
        log_fn=print,
        absent_poll_sec: float = 10.0,
        on_status=None,
    ):
        super().__init__(daemon=True, name="op25_client")
        urls = [url] if isinstance(url, str) else list(url)
        self.urls = []
        for u in urls:
            u = u.rstrip("/") + "/"
            if u not in self.urls:
                self.urls.append(u)
        self.on_update = on_update
        self.on_status = on_status
        self.poll_sec = poll_sec
        self.absent_poll_sec = absent_poll_sec
        self.timeout_sec = timeout_sec
        self.log_fn = log_fn
        self._stop_evt = threading.Event()
        self._last_fingerprint = None
        self._misses = 0
        self._said_absent = False
        self.active_url = None      # the address answering, while one is
        self.reachable = False

    @property
    def url(self):
        """Where to send: the address answering, else the last configured."""
        return self.active_url or self.urls[-1]

    def stop(self) -> None:
        self._stop_evt.set()

    def run(self) -> None:
        while not self._stop_evt.is_set():
            candidates = [self.active_url] if self.active_url else self.urls
            answered = None
            status = None
            for url in candidates:
                msgs, status = self._poll(url)
                if status == "ok":
                    answered = url
                    break
            if answered:
                self._misses = 0
                if not self.reachable:
                    self._set_reachable(True, answered)
                for state in self._extract_systems(msgs):
                    fp = self._fingerprint(state)
                    if fp == self._last_fingerprint:
                        continue
                    self._last_fingerprint = fp
                    try:
                        self.on_update(state)
                    except Exception as e:
                        self.log_fn("op25_client: on_update raised: %s" % e)
            elif self.reachable:
                self._misses += 1
                if self._misses >= self.LOST_AFTER:
                    self.log_fn("op25_client: lost %s (%s)" % (self.active_url, status))
                    self._set_reachable(False, None)
            elif not self._said_absent:
                self._said_absent = True
                self.log_fn("op25_client: no op25 at %s (%s); looking every %.0fs"
                            % (", ".join(self.urls), status, self.absent_poll_sec))
            self._stop_evt.wait(self.poll_sec if self.reachable else self.absent_poll_sec)

    def _set_reachable(self, reachable: bool, url) -> None:
        self.reachable = reachable
        self.active_url = url
        if reachable:
            self.log_fn("op25_client: op25 answering at %s" % url)
            self._said_absent = False
        if self.on_status:
            try:
                self.on_status(reachable, url)
            except Exception as e:
                self.log_fn("op25_client: on_status raised: %s" % e)

    def _poll(self, url):
        # http_server.py expects a LIST of command dicts; a bare dict iterates over keys and crashes.
        body = json.dumps([{"command": "update", "arg1": 0, "arg2": 0}]).encode()
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                return json.loads(resp.read().decode("utf-8", errors="replace")), "ok"
        except urllib.error.URLError as ex:
            return [], "connect-error: %s" % ex.reason
        except (json.JSONDecodeError, ValueError):
            return [], "bad-json"
        except Exception as ex:
            return [], "error: %s" % ex

    def _extract_systems(self, msgs):
        if not isinstance(msgs, list):
            return
        for d in msgs:
            if not isinstance(d, dict) or d.get("json_type") != "trunk_update":
                continue
            nac = d.get("nac")
            if nac is None:
                continue
            sysd = d.get(str(nac)) or d.get(nac)
            if not isinstance(sysd, dict):
                continue
            wacn = sysd.get("wacn", 0) or 0
            sysid = sysd.get("sysid", 0) or 0
            rxchan = sysd.get("rxchan", 0) or 0
            if not (wacn and sysid and rxchan):
                continue
            adj = sysd.get("adjacent_data", {}) or {}
            adjacents = tuple(
                Adjacent(
                    cc_freq_hz=int(freq),
                    rfid=int((entry or {}).get("rfid", 0) or 0),
                    stid=int((entry or {}).get("stid", 0) or 0),
                    uplink_hz=int((entry or {}).get("uplink", 0) or 0),
                )
                for freq, entry in adj.items()
            )
            yield Op25SystemState(
                nac=int(nac),
                wacn=int(wacn),
                sysid=int(sysid),
                rfid=int(sysd.get("rfid", 0) or 0),
                stid=int(sysd.get("stid", 0) or 0),
                cc_freq_hz=int(rxchan),
                tx_freq_hz=int(sysd.get("txchan", 0) or 0),
                adjacents=adjacents,
            )

    def _fingerprint(self, state: Op25SystemState):
        return (
            state.cc_freq_hz, state.nac, state.wacn, state.sysid,
            state.rfid, state.stid,
            tuple(sorted((a.cc_freq_hz, a.rfid, a.stid) for a in state.adjacents)),
        )
