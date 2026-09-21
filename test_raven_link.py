"""raven_link, checked against a stand-in for RAVEN's API.

A small HTTP server in a thread answers the two calls the way RAVEN does,
and records what it was asked, so the hand-off can be checked without a
HackRF or a running RAVEN. Run it directly: python test_raven_link.py
"""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

os.environ["RAVEN_URL"] = "http://127.0.0.1:0/"       # replaced once the stub has a port
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import raven_link  # noqa: E402

asked = []
listening = {"on": False}


class Stub(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _reply(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/api/health":
            return self._reply(200, {"ok": True, "version": "stub"})
        self._reply(404, {"ok": False})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)) or 0) or b"{}")
        asked.append((self.path, body))
        if self.path == "/api/tune":
            if body.get("mode") not in ("nfm", "wfm", "am", "usb", "lsb"):
                return self._reply(400, {"ok": False, "reason": "unknown mode"})
            return self._reply(200, {"ok": True, "applied": "live" if listening["on"] else "wanted"})
        if self.path == "/api/memories":
            return self._reply(200, {"ok": True, "memory": {"id": 7, "name": body.get("name"), "mhz": body.get("mhz")}})
        self._reply(404, {"ok": False, "reason": "no such call"})


failed = 0


def check(label, got, want):
    global failed
    ok = got == want
    failed += not ok
    print(("ok   " if ok else "FAIL ") + label + ("" if ok else "  got %r want %r" % (got, want)))


# --- the cells, as the tables write them
check("output cell", raven_link.megahertz("147.225 MHz"), 147.225)
check("bare number", raven_link.megahertz("162.550"), 162.55)
check("slash pair takes the first", raven_link.megahertz("146.52/146.55"), 146.52)
check("no number", raven_link.megahertz("simplex"), None)
check("a tone is not a frequency", raven_link.megahertz("100.0 Hz"), None)
check("FM", raven_link.mode_for("FM"), "nfm")
check("USB", raven_link.mode_for("USB"), "usb")
check("LSB", raven_link.mode_for("lsb"), "lsb")
check("SSB on 40 m is lower", raven_link.mode_for("SSB", 7.2), "lsb")
check("CW/SSB on 20 m is upper", raven_link.mode_for("CW/SSB", 14.2), "usb")
check("AM", raven_link.mode_for("AM"), "am")
check("empty is nfm", raven_link.mode_for(None), "nfm")
check("nonsense is nfm", raven_link.mode_for("digital"), "nfm")

# --- the calls, against the stub
server = HTTPServer(("127.0.0.1", 0), Stub)
threading.Thread(target=server.serve_forever, daemon=True).start()
raven_link.URL = "http://127.0.0.1:%d/" % server.server_port

check("answering", raven_link.answering(), True)
message, reason = raven_link.tune(147.225, "nfm")
check("tune queued", (reason, "when its console starts listening" in message), ("", True))
check("tune asked for", asked[-1], ("/api/tune", {"freq_mhz": 147.225, "mode": "nfm"}))
listening["on"] = True
message, reason = raven_link.tune(162.55, "nfm")
check("tune live", (reason, message), ("", "RAVEN is on 162.5500 MHz NFM"))
message, reason = raven_link.tune(162.55, "dstar")
check("bad mode is a reason", (message, reason), ("", "unknown mode"))
message, reason = raven_link.remember("W0ABC", 147.225, "nfm")
check("remember", (reason, message), ("", "W0ABC is in RAVEN's memories at 147.2250 MHz"))
check("remember asked for", asked[-1], ("/api/memories", {"name": "W0ABC", "mhz": 147.225, "mode": "nfm"}))

server.shutdown()
raven_link.URL = "http://127.0.0.1:1/"
check("not answering", raven_link.answering(), False)
message, reason = raven_link.tune(147.225)
check("not answering is a reason", (message, reason.startswith("RAVEN is not answering")), ("", True))

print("%d failed" % failed if failed else "all passed")
sys.exit(1 if failed else 0)
