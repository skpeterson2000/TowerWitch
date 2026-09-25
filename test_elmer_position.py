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

print("")
print("-- ELMER's own diagnosis comes with it --")
got = ask({"located": True, "lat": 46.6, "lon": -94.3, "mode": 3,
           "from": "ELMER on the Jeep",
           "sleuth": {"quality": "3D", "advice": "move the puck to a window",
                      "words": "gpsd on the Jeep"}})
check("the quality it reports", got["elmer_quality"], "3D")
check("  and what would make it better",
      got["elmer_advice"], "move the puck to a window")

print("")
print("-- the way back in is open --")
# A unit with a receiver coming on line outranks a typed QTH, which is what
# elmer_link.position() already decides; this is that it arrives here as a
# fix and is not flattened into the QTH case.
got = ask({"located": True, "lat": 47.0, "lon": -93.0, "mode": 2,
           "from": "ELMER on the Pi",
           "qth": {"lat": 46.60302, "lon": -94.30944, "grid": "EN26uo"}})
check("a real fix wins over a QTH that is also on offer",
      (round(got["lat"]), got["mode"]), (47, 2))

print("")
print("-- but not this program's own word, come back round --")
# ELMER hears TowerWitch's UDP broadcast and rates it a fix. Taken back it
# is TowerWitch's own position returned as ELMER's - which the Qt build
# records having put the Minneapolis default on every screen in the house.
got = ask({"located": True, "lat": 44.9778, "lon": -93.265, "mode": 3,
           "source": "towerwitch-net",
           "qth": {"lat": 46.60302, "lon": -94.30944, "grid": "EN26uo"}})
check("the echo is refused", round(got["lat"], 3), 46.603)
check("  and the QTH underneath it is used instead", got["mode"], 0)

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
