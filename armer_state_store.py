"""
armer_state_store.py - TowerWitch's system of record for ARMER sites.

Blends static CSV seed data (rfid, stid, per-site nac, lat/lon, control
channel frequencies) with live op25 observations (wacn, sysid, last_seen
timestamps). The "Send to OP25" button reads from here at press time so
the assembled payload is highest-confidence available.

JSON shape (data/armer_state.json):
  {
    "sites": {
      "<rfid>-<stid>": {
        "site_id_key": "1-1",
        "rfid": 1, "stid": 1, "stid_hex": "0x1",
        "nac": "0x190",                  # from CSV (decimal -> hex string)
        "description": "...", "county": "...",
        "lat": ..., "lon": ..., "range_mi": ...,
        "cc_freqs_hz": [858237500, ...], # 'c'-marked CSV columns
        "all_freqs_hz": [...],
        "wacn": null,                    # filled by op25 observation
        "sysid": null,
        "last_seen_ts": null,
        "confidence": "csv_only"         # csv_only|observed_directly|observed_as_adjacent
      },
      ...
    },
    "network": {                          # WACN/SYSID are shared across an ARMER network
      "wacn": null,
      "sysid": null,
      "last_seen_ts": null
    },
    "meta": {
      "csv_source": "trs_sites_3508.csv",
      "bootstrap_ts": ...
    }
  }
"""

from __future__ import annotations

import csv
import json
import os
import tempfile
import threading
import time
from typing import Optional


CONFIDENCE_CSV_ONLY            = "csv_only"
CONFIDENCE_OBSERVED_AS_ADJ     = "observed_as_adjacent"
CONFIDENCE_OBSERVED_DIRECTLY   = "observed_directly"


_lock = threading.Lock()


def _site_key(rfid: int, stid: int) -> str:
    return "%d-%d" % (int(rfid), int(stid))


def _parse_freq_to_hz(token: str) -> Optional[int]:
    """Parse '858.237500c' or '858.2375' to int Hz. Strips 'c' marker."""
    if not token:
        return None
    t = token.strip().lower().rstrip("c").strip()
    if not t:
        return None
    try:
        return int(round(float(t) * 1_000_000))
    except ValueError:
        return None


def _row_freqs(row: list) -> tuple[list, list]:
    """Return (cc_freqs_hz, all_freqs_hz) from columns 9 onward."""
    cc, all_ = [], []
    for tok in row[9:]:
        if not tok:
            continue
        hz = _parse_freq_to_hz(tok)
        if hz is None:
            continue
        all_.append(hz)
        if "c" in tok.lower():
            cc.append(hz)
    return cc, all_


def bootstrap_from_csv(csv_path: str, json_path: str) -> dict:
    """Read CSV, write initial armer_state.json. Returns the resulting state.

    Idempotent on the CSV-derived fields: re-running rewrites static fields
    but PRESERVES live-observation fields (wacn, sysid, last_seen_ts,
    confidence if better than csv_only).
    """
    existing = _safe_load(json_path) or {}
    existing_sites = existing.get("sites", {})

    sites: dict = {}
    with open(csv_path, newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        for row in reader:
            if len(row) < 10 or not row[0].strip():
                continue
            try:
                rfid = int(row[0])
                stid = int(row[1])
                stid_hex = (row[2] or "").strip()
                nac_dec = int(row[3]) if row[3].strip() else 0
                description = (row[4] or "").strip()
                county = (row[5] or "").strip()
                lat = float(row[6]) if row[6].strip() else None
                lon = float(row[7]) if row[7].strip() else None
                range_mi = float(row[8]) if row[8].strip() else None
            except (ValueError, IndexError):
                continue

            cc_freqs, all_freqs = _row_freqs(row)
            key = _site_key(rfid, stid)
            prev = existing_sites.get(key, {})

            sites[key] = {
                "site_id_key": key,
                "rfid": rfid,
                "stid": stid,
                "stid_hex": stid_hex or ("0x%x" % stid),
                "nac": "0x%x" % nac_dec if nac_dec else None,
                "description": description,
                "county": county,
                "lat": lat,
                "lon": lon,
                "range_mi": range_mi,
                "cc_freqs_hz": cc_freqs,
                "all_freqs_hz": all_freqs,
                "wacn": prev.get("wacn"),
                "sysid": prev.get("sysid"),
                "last_seen_ts": prev.get("last_seen_ts"),
                "confidence": prev.get("confidence", CONFIDENCE_CSV_ONLY),
            }

    state = {
        "sites": sites,
        "network": existing.get("network", {"wacn": None, "sysid": None, "last_seen_ts": None}),
        "meta": {
            "csv_source": os.path.basename(csv_path),
            "bootstrap_ts": time.time(),
            "site_count": len(sites),
        },
    }
    _atomic_write(json_path, state)
    return state


def load(json_path: str) -> dict:
    with _lock:
        return _safe_load(json_path) or _empty_state()


def get_site(json_path: str, rfid: int, stid: int) -> Optional[dict]:
    state = load(json_path)
    return state.get("sites", {}).get(_site_key(rfid, stid))


def update_from_op25(json_path: str, system_state) -> None:
    """Merge an Op25SystemState (or compatible dict) into the JSON state."""
    with _lock:
        state = _safe_load(json_path) or _empty_state()
        sites = state.setdefault("sites", {})
        network = state.setdefault("network", {})
        now = time.time()

        # Network-level WACN/SYSID are shared across the ARMER network.
        wacn = _as_int(getattr(system_state, "wacn", None))
        sysid = _as_int(getattr(system_state, "sysid", None))
        if wacn:
            network["wacn"] = "0x%x" % wacn
        if sysid:
            network["sysid"] = "0x%x" % sysid
        if wacn or sysid:
            network["last_seen_ts"] = now

        # Directly-observed site: the one op25 is currently locked on.
        rfid = _as_int(getattr(system_state, "rfid", 0))
        stid = _as_int(getattr(system_state, "stid", 0))
        if rfid and stid:
            key = _site_key(rfid, stid)
            site = sites.get(key, {"rfid": rfid, "stid": stid, "site_id_key": key,
                                    "confidence": CONFIDENCE_CSV_ONLY})
            site["wacn"] = network.get("wacn")
            site["sysid"] = network.get("sysid")
            site["last_seen_ts"] = now
            site["confidence"] = CONFIDENCE_OBSERVED_DIRECTLY
            sites[key] = site

        # Adjacent sites: op25 has heard their CCs broadcast.
        for adj in getattr(system_state, "adjacents", []) or []:
            arfid = _as_int(getattr(adj, "rfid", 0))
            astid = _as_int(getattr(adj, "stid", 0))
            if not (arfid and astid):
                continue
            akey = _site_key(arfid, astid)
            site = sites.get(akey, {"rfid": arfid, "stid": astid, "site_id_key": akey,
                                     "confidence": CONFIDENCE_CSV_ONLY})
            site["wacn"] = network.get("wacn")
            site["sysid"] = network.get("sysid")
            site["last_seen_ts"] = now
            if site.get("confidence") != CONFIDENCE_OBSERVED_DIRECTLY:
                site["confidence"] = CONFIDENCE_OBSERVED_AS_ADJ
            sites[akey] = site

        _atomic_write(json_path, state)


# --- helpers ---

def _empty_state() -> dict:
    return {"sites": {}, "network": {"wacn": None, "sysid": None, "last_seen_ts": None}, "meta": {}}


def _safe_load(json_path: str) -> Optional[dict]:
    if not os.path.exists(json_path):
        return None
    try:
        with open(json_path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _atomic_write(json_path: str, data: dict) -> None:
    tmp_dir = os.path.dirname(json_path) or "."
    fd, tmp_path = tempfile.mkstemp(dir=tmp_dir, prefix=".armer_state_", suffix=".json")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, sort_keys=True)
        os.replace(tmp_path, json_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _as_int(v) -> int:
    if v is None:
        return 0
    if isinstance(v, str):
        try:
            return int(v, 0)
        except ValueError:
            return 0
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0
