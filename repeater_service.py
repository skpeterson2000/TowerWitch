#!/usr/bin/env python3
"""Serve TowerWitch's repeater knowledge to ELMER over the network.

Two Pis in one vehicle: only one has TowerWitch and the RadioReference
credentials. The other still needs to know what is on the air around here, and
copying a CSV between them by hand at a campsite is not a plan. ELMER already
has the client half - `--towerwitch-url` and `repeaters.from_service()` - and
has had it since "Make Contact"; this is the half that answers.

The reply is deliberately the same shape TowerWitch already writes into
radio_cache: an object with a `data` list. That is the format ELMER's parser
was written against, so nothing on either side has to learn a new one.

Nothing here looks anything up. It serves what TowerWitch has already found -
the cached lookups and the RepeaterBook exports on disk - because the
subscription and the credentials are TowerWitch's to hold, not this service's
to spend on behalf of whoever asks.
"""
import csv
import json
import logging
import math
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parent
HOST = "0.0.0.0"
PORT = 8137
MAX_RADIUS_KM = 500.0
DEFAULT_RADIUS_KM = 100.0

log = logging.getLogger("repeater_service")

# Parsed rows are held until something on disk changes. A lookup TowerWitch
# does while parked writes a new cache file, and the next request picks it up
# without a restart - which matters, because the whole point is that the other
# Pi asks about wherever the vehicle has got to.
_cache = {"stamp": None, "rows": []}


def great_circle(lat1, lon1, lat2, lon2):
    """Kilometres between two points, haversine on a sphere."""
    radius = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = (math.sin(dp / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2)
    return 2 * radius * math.asin(min(1.0, math.sqrt(a)))


def _num(value):
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _entry(call, output, **kw):
    """One repeater in the radio_cache shape, or None if it is not one.

    A row with no callsign or no coordinate cannot be drawn on a bearing, and
    an entry ELMER has to throw away is better not sent.
    """
    call = str(call or "").strip().upper()
    output = _num(output)
    if not call or output is None or not 28.0 <= output <= 1300.0:
        return None
    if kw.get("lat") is None or kw.get("lon") is None:
        return None
    entry = {"call": call, "frequency": round(output, 4),
             "output": round(output, 4), "input": None, "offset": None,
             "tone": None, "pl_tone": None, "lat": None, "lon": None,
             "location": "", "description": ""}
    entry.update({k: v for k, v in kw.items() if k in entry})
    return entry


def _places():
    """TowerWitch's town coordinates, better than a county centroid."""
    try:
        raw = json.loads((ROOT / "data" / "location_coordinates.json").read_text())
    except (OSError, ValueError):
        return {}
    out = {}
    for key, value in (raw or {}).items():
        lat, lon = _num((value or {}).get("lat")), _num((value or {}).get("lon"))
        if lat is not None and lon is not None:
            out[str(key).strip().lower()] = (lat, lon)
    return out


def _town_key(location, county, state):
    """RepeaterBook writes a site, not a town: "Nisswa - WJJY Tower"."""
    town = str(location or "").split(" - ")[0].split(",")[0].strip().lower()
    return (f"{town}|{str(county or '').strip().lower()}"
            f"|{str(state or '').strip().lower()}", town)


def _from_csv(path, places):
    """A RepeaterBook export, placed to the town where the town is known."""
    out = []
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            for line in csv.DictReader(handle):
                lat, lon = _num(line.get("Latitude")), _num(line.get("Longitude"))
                if lat is None or lon is None:
                    continue
                county = (line.get("County") or "").strip()
                key, town = _town_key(line.get("Location"), county,
                                      line.get("State"))
                # A county centroid puts five machines in five towns at one
                # identical bearing. Where the town itself is known, use it.
                if key in places and town and town != county.lower():
                    lat, lon = places[key]
                tone = (line.get("Uplink Tone")
                        or line.get("Downlink Tone") or "").strip()
                entry = _entry(
                    line.get("Call"), line.get("Output Freq"),
                    input=_num(line.get("Input Freq")),
                    offset=_num(line.get("Offset")),
                    tone=tone or None, pl_tone=_num(tone),
                    lat=lat, lon=lon,
                    location=(line.get("Location") or "").strip(),
                    description=(line.get("Modes") or "").strip())
                if entry:
                    out.append(entry)
    except (OSError, csv.Error) as problem:
        log.warning("could not read %s: %s", path.name, problem)
    return out


def _from_cache(path):
    """One of TowerWitch's own cached lookups, already in the right shape."""
    try:
        payload = json.loads(path.read_text())
    except (OSError, ValueError) as problem:
        log.warning("could not read %s: %s", path.name, problem)
        return []
    rows = payload.get("data") if isinstance(payload, dict) else payload
    out = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        entry = _entry(row.get("call"),
                       row.get("output") or row.get("frequency"),
                       input=_num(row.get("input")),
                       offset=_num(row.get("offset")),
                       tone=row.get("tone"), pl_tone=_num(row.get("pl_tone")),
                       lat=_num(row.get("lat")), lon=_num(row.get("lon")),
                       location=(row.get("location") or "").strip(),
                       description=(row.get("description") or "").strip())
        if entry:
            out.append(entry)
    return out


def _stamp():
    """When anything TowerWitch writes last changed."""
    newest = 0.0
    count = 0
    for folder in ("data", "radio_cache"):
        here = ROOT / folder
        if not here.is_dir():
            continue
        for item in here.iterdir():
            try:
                newest = max(newest, item.stat().st_mtime)
                count += 1
            except OSError:
                continue
    return (newest, count)


def _dedupe(rows):
    """One entry per machine, per frequency."""
    best = {}
    for row in rows:
        best.setdefault((row["call"], round(row["output"], 3)), row)
    return sorted(best.values(), key=lambda r: (r["output"], r["call"]))


def everything():
    """Every repeater TowerWitch knows the position of."""
    stamp = _stamp()
    if _cache["stamp"] == stamp:
        return _cache["rows"]
    places = _places()
    rows = []
    data = ROOT / "data"
    if data.is_dir():
        # Enriched exports first: the same rows, with coordinates already on.
        for path in sorted(data.glob("*_enriched.csv")):
            rows += _from_csv(path, places)
        for path in sorted(data.glob("*.csv")):
            if not path.name.endswith("_enriched.csv"):
                rows += _from_csv(path, places)
    cache = ROOT / "radio_cache"
    if cache.is_dir():
        for path in sorted(cache.glob("repeaters_*.json")):
            rows += _from_cache(path)
    rows = _dedupe(rows)
    _cache.update({"stamp": stamp, "rows": rows})
    log.info("loaded %d repeaters from disk", len(rows))
    return rows


def near(lat, lon, radius_km):
    """What is within reach of a position, nearest first."""
    out = []
    for row in everything():
        away = great_circle(lat, lon, row["lat"], row["lon"])
        if away <= radius_km:
            found = dict(row)
            found["distance_km"] = round(away, 1)
            out.append(found)
    return sorted(out, key=lambda r: r["distance_km"])


class Handler(BaseHTTPRequestHandler):
    server_version = "TowerWitch/1.0"

    def _send(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        # The asking Pi is a browser-side fetch in some setups; this costs
        # nothing and saves an afternoon of wondering why.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        route = urlparse(self.path)
        query = parse_qs(route.query)

        if route.path in ("/", "/api", "/api/health"):
            return self._send(200, {"service": "TowerWitch repeater service",
                                    "repeaters": len(everything()),
                                    "endpoints": ["/api/repeaters"]})

        if route.path != "/api/repeaters":
            return self._send(404, {"error": "no such endpoint",
                                    "endpoints": ["/api/repeaters"]})

        lat = _num((query.get("lat") or [None])[0])
        lon = _num((query.get("lon") or [None])[0])
        if lat is None or lon is None or not -90 <= lat <= 90 or not -180 <= lon <= 180:
            return self._send(400, {"error": "lat and lon are required, "
                                             "in degrees"})
        radius = _num((query.get("radius_km") or [None])[0]) or DEFAULT_RADIUS_KM
        radius = max(1.0, min(MAX_RADIUS_KM, radius))

        rows = near(lat, lon, radius)
        log.info("%s asked about %.4f,%.4f within %.0f km - sent %d",
                 self.client_address[0], lat, lon, radius, len(rows))
        # The radio_cache shape, unchanged: ELMER's parser already reads it.
        self._send(200, {"timestamp": datetime.now().isoformat(),
                         "data_type": "repeaters",
                         "location_key": f"{lat:.3f}_{lon:.3f}_{int(radius)}",
                         "data": rows})

    def log_message(self, fmt, *args):
        # BaseHTTPRequestHandler writes to stderr by default; route it through
        # logging so journalctl carries it like everything else.
        log.debug("%s %s", self.client_address[0], fmt % args)


def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s - %(levelname)s - %(message)s")
    total = len(everything())
    log.info("TowerWitch repeater service on %s:%d - %d repeaters ready",
             HOST, PORT, total)
    if not total:
        log.warning("nothing on disk carried both a callsign and a "
                    "coordinate - ELMER will get empty answers")
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.daemon_threads = True
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("stopped")
        server.server_close()


if __name__ == "__main__":
    main()
