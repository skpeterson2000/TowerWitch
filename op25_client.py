"""
op25_client.py - background poller for a running op25 multi_rx HTTP terminal.

Polls every 250ms (matching op25's web UI refresh), parses trunk_update
messages, fires a callback with each new SystemState observation.

Modeled on op25's own sniffer_http.py reference implementation.

Usage from TowerWitch:
    from op25_client import Op25Client
    from armer_state_store import update_from_op25

    client = Op25Client(
        url="http://192.168.1.31:8080/",
        on_update=lambda st: update_from_op25(json_path, st),
    )
    client.start()
    ...
    client.stop()
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
    def __init__(
        self,
        url: str,
        on_update,
        poll_sec: float = 0.25,
        timeout_sec: float = 2.0,
        log_fn=print,
    ):
        super().__init__(daemon=True, name="op25_client")
        self.url = url.rstrip("/") + "/"
        self.on_update = on_update
        self.poll_sec = poll_sec
        self.timeout_sec = timeout_sec
        self.log_fn = log_fn
        self._stop_evt = threading.Event()
        self._last_status = None
        self._last_status_print = 0.0
        self._last_fingerprint = None

    def stop(self) -> None:
        self._stop_evt.set()

    def run(self) -> None:
        while not self._stop_evt.is_set():
            msgs, status = self._poll()
            now = time.time()
            if status != "ok":
                if status != self._last_status or now - self._last_status_print > 5:
                    self.log_fn("op25_client: %s" % status)
                    self._last_status = status
                    self._last_status_print = now
            else:
                self._last_status = "ok"
                for state in self._extract_systems(msgs):
                    fp = self._fingerprint(state)
                    if fp == self._last_fingerprint:
                        continue
                    self._last_fingerprint = fp
                    try:
                        self.on_update(state)
                    except Exception as e:
                        self.log_fn("op25_client: on_update raised: %s" % e)
            self._stop_evt.wait(self.poll_sec)

    def _poll(self):
        # http_server.py expects a LIST of command dicts; a bare dict iterates over keys and crashes.
        body = json.dumps([{"command": "update", "arg1": 0, "arg2": 0}]).encode()
        req = urllib.request.Request(
            self.url, data=body,
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
