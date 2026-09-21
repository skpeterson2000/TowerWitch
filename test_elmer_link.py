"""elmer_link: hearing every ELMER on the network, and borrowing the
right one's fix. The greetings are ELMER's own shape (elmer/discovery.py),
made up here; the local ELMER is a stand-in HTTP server so the order of
preference can be checked without any ELMER running. No network.
Run it directly: python test_elmer_link.py
"""
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import elmer_link  # noqa: E402

failed = 0


def check(label, got, want):
    global failed
    ok = got == want
    failed += not ok
    print(("ok   " if ok else "FAIL ") + label + ("" if ok else "  got %r want %r" % (got, want)))


def greeting(unit, name, address, gps=None, magic="elmer-unit"):
    body = {"elmer": magic, "unit": unit, "name": name, "url": "http://%s:5000" % address, "version": "x",
            "sent": time.time(), "party": {}, "net": {}}
    if gps:
        body["gps"] = gps
    return json.dumps(body).encode(), address


# --- one greeting
peer = elmer_link.parse_announcement(*greeting("u1", "SaintPaul", "192.168.1.119",
                                               {"lat": 46.6, "lon": -94.3, "mode": 3, "source": "gps", "age_s": 0.4}))
check("a greeting with a fix", (peer["name"], peer["url"], peer["gps"]["lat"], peer["gps"]["source"]),
      ("SaintPaul", "http://192.168.1.119:5000", 46.6, "gps"))
peer = elmer_link.parse_announcement(*greeting("u2", "Laptop", "192.168.1.177"))
check("a greeting without one", (peer["name"], peer["gps"]), ("Laptop", None))
check("not ELMER's word", elmer_link.parse_announcement(*greeting("u3", "x", "1.2.3.4", magic="other")), None)
check("not JSON", elmer_link.parse_announcement(b"\xff\xfe", "1.2.3.4"), None)
peer = elmer_link.parse_announcement(*greeting("u4", "Bad", "1.2.3.4", {"lat": 200, "lon": 0}))
check("an impossible fix is dropped, the ELMER kept", (peer["name"], peer["gps"]), ("Bad", None))

# --- which neighbour to borrow from
n = elmer_link.Neighbours()
now = time.time()
for args in (("a", "NoFix", "10.0.0.1"),
             ("b", "Borrower", "10.0.0.2", {"lat": 1, "lon": 1, "source": "elmer-peer", "age_s": 1}),
             ("c", "FromTW", "10.0.0.3", {"lat": 2, "lon": 2, "source": "towerwitch-net", "age_s": 1}),
             ("d", "Puck", "10.0.0.4", {"lat": 46.6, "lon": -94.3, "mode": 3, "source": "gps", "age_s": 5}),
             ("e", "Phone", "10.0.0.5", {"lat": 46.7, "lon": -94.4, "mode": 2, "source": "phone", "age_s": 1})):
    p = elmer_link.parse_announcement(*greeting(*args))
    n.peers[p["unit"]] = p
check("everyone heard is current", len(n.current(now)), 5)
check("the freshest fix of an ELMER's own wins", n.with_fix(now)["name"], "Phone")
n.peers["e"]["heard_at"] = now - 60
check("a unit gone quiet drops out", n.with_fix(now)["name"], "Puck")
n.peers["d"]["heard_at"] = now - 60
check("borrowed and TowerWitch-relayed fixes are never taken", n.with_fix(now), None)
check("an empty room", elmer_link.Neighbours().with_fix(), None)

# --- position(): the local ELMER first, then the network
answer = {"located": False, "reason": "no fix", "qth": {"lat": 45.0, "lon": -93.0, "short": "home"}, "sleuth": {}}


class Stub(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        data = json.dumps(answer).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


server = HTTPServer(("127.0.0.1", 0), Stub)
threading.Thread(target=server.serve_forever, daemon=True).start()
elmer_link.URL = "http://127.0.0.1:%d/" % server.server_port
elmer_link._neighbours = None
check("no fix anywhere: the local QTH comes through", elmer_link.position()["qth"]["short"], "home")
heard = elmer_link.Neighbours()
p = elmer_link.parse_announcement(*greeting("d", "Puck", "10.0.0.4",
                                            {"lat": 46.6, "lon": -94.3, "mode": 3, "source": "gps", "age_s": 5}))
heard.peers["d"] = p
elmer_link._neighbours = heard
got = elmer_link.position()
check("local ELMER has no fix: a neighbour's is taken", (got["located"], got["lat"], got["source"], got["from"]),
      (True, 46.6, "elmer-peer", "ELMER on Puck at 10.0.0.4"))
answer = {"located": True, "lat": 46.61, "lon": -94.31, "source": "phone", "from": "phone", "sleuth": {}}
check("local ELMER located: it wins over the network", elmer_link.position()["lat"], 46.61)
server.shutdown()
elmer_link.URL = "http://127.0.0.1:1/"
check("no local ELMER at all: the network still answers", elmer_link.position()["from"], "ELMER on Puck at 10.0.0.4")
elmer_link._neighbours = None
check("no ELMER anywhere", elmer_link.position(), None)

print("%d failed" % failed if failed else "all passed")
sys.exit(1 if failed else 0)
