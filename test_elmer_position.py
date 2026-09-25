"""TowerWitch borrows a position from ELMER when there is no gpsd here.

Run it directly: python test_elmer_position.py

The receiver is on the Pi in the vehicle and the laptop on the desk has
none, which used to mean the laptop invented a position in Minneapolis and
labelled it DEMO. ELMER is on that desk and has the inputs for typing a
QTH into, so it is asked instead. elmer_link.py could already do this and
was never called by anything.

What matters here is the shaping, and that a borrowed position is marked
as borrowed: it is not this program's fix, it is not broadcast as one, and
the wall does not call it GPS.
"""
import sys

import TowerWitch_Tkinter as tw
import elmer_link

FAILS = []


def check(label, got, want):
    ok = got == want
    print("  %s  %s: %r%s" % ("ok  " if ok else "FAIL", label, got,
                              "" if ok else "  (wanted %r)" % (want,)))
    if not ok:
        FAILS.append(label)


def ask(answer):
    """What the worker makes of one answer from ELMER."""
    real = elmer_link.position
    elmer_link.position = lambda timeout=2.0: answer
    try:
        return tw.GPSWorker._ask_elmer(tw.GPSWorker.__new__(tw.GPSWorker))
    finally:
        elmer_link.position = real


print("\n-- a real fix, from ELMER's own receiver or a neighbour --")
got = ask({"located": True, "lat": 46.6, "lon": -94.3, "mode": 3,
           "from": "ELMER on the Jeep"})
check("the position is taken", (got["lat"], got["lon"]), (46.6, -94.3))
check("  with the mode it came with", got["mode"], 3)
check("  marked as ELMER's", got["source"], "elmer")
check("  and says whose", got["elmer_words"], "ELMER on the Jeep")
check("  it is not a demo", got["demo"], False)

print("\n-- no fix anywhere, but somebody typed a QTH in --")
got = ask({"located": False, "qth": {"lat": 46.60302, "lon": -94.30944,
                                     "grid": "EN26uo", "short": "Pequot Lakes"}})
check("the QTH is taken", (round(got["lat"], 3), round(got["lon"], 3)),
      (46.603, -94.309))
check("  at mode nought - a place named, not a fix", got["mode"], 0)
check("  and says so", got["elmer_words"], "ELMER's QTH EN26uo")

print("\n-- and when there is nothing to take --")
check("no ELMER at all", ask(None), None)
check("  an ELMER with neither fix nor QTH",
      ask({"located": False, "qth": None}), None)
check("  a QTH with no position in it",
      ask({"located": False, "qth": {"grid": "EN26uo"}}), None)

print("\n-- a link that throws does not stop the GPS loop --")


def boom(timeout=2.0):
    raise OSError("network is down")


real = elmer_link.position
elmer_link.position = boom
try:
    check("it comes back empty-handed rather than raising",
          tw.GPSWorker._ask_elmer(tw.GPSWorker.__new__(tw.GPSWorker)), None)
finally:
    elmer_link.position = real

print("\n-- borrowed is not broadcast --")
# send_udp_armer_data does: ours = position_source in ('gps', 'manual').
# A borrowed position is neither, so the packet carries no position and
# ELMER is never handed back its own answer as though it were news - the
# same guard ELMER keeps against passing on an "elmer-peer" fix.
check("'elmer' is not one of the sources TowerWitch calls its own",
      "elmer" in ("gps", "manual"), False)

print("\n" + ("ALL PASS" if not FAILS else "FAILURES: %s" % (FAILS,)))
sys.exit(1 if FAILS else 0)
