"""HallPass, from TowerWitch: saying hello to the room.

HallPass is the suite's control room - a wall of tiles, one per member per
machine, each with a line of what that member is doing. A member is on the
wall by greeting udp/12348 every few seconds; the shape is HallPass's
DESIGN.md and is spelled out here rather than imported, so TowerWitch
needs nothing installed from HallPass to be seen by it. Nothing is
configured: HallPass hears the greeting or it does not, and TowerWitch
never learns whether it did.

What TowerWitch tells the room is what it is for: where the station is
and how it knows, and the nearest ARMER site. That is the line under its
name on the wall.
"""
import json
import socket
import threading
import time

PORT = 12348
EVERY = 5.0


def broadcast_targets():
    """Where a broadcast has to go to reach every segment this machine is on.

    The limited broadcast, 255.255.255.255, leaves by one interface only -
    whichever holds the default route this minute. A Pi with Ethernet and
    wifi both up, or a tether beside the wifi, announces down the wrong one
    and is heard by nobody on the other: ELMER found this on its bench, and
    TowerWitch's position broadcast had the same fault for as long as it
    existed. The directed broadcast of each interface goes to that segment
    regardless, so every segment hears it. Without `ip` - Windows - the
    limited broadcast is the whole list, which is what always happened.
    """
    out = []
    try:
        import subprocess
        text = subprocess.run(["ip", "-4", "-br", "addr"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        text = ""
    for row in text.splitlines():
        parts = row.split()
        if len(parts) < 3 or parts[1] != "UP":
            continue
        for cidr in parts[2:]:
            try:
                import ipaddress
                iface = ipaddress.IPv4Interface(cidr)
            except ValueError:
                continue
            if iface.ip.is_loopback or iface.network.prefixlen >= 31:
                continue
            addr = str(iface.network.broadcast_address)
            if addr not in out:
                out.append(addr)
    out.append("255.255.255.255")
    return out


def my_address():
    """This machine's LAN address, by asking which interface would route out; loopback if none."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        addr = s.getsockname()[0]
        s.close()
        return addr
    except OSError:
        return "127.0.0.1"


def greeting(state="", url="", version="", alarm=None, holding=None, monitors=None, machine=None):
    body = {"hallpass": 1, "member": "towerwitch", "name": "TowerWitch", "role": "towers",
            "machine": machine or socket.gethostname(), "url": url, "version": version, "state": state,
            "sent": time.time()}
    if holding:
        body["holding"] = holding
    if alarm:
        body["alarm"] = alarm
    if monitors:
        body["monitors"] = monitors
    return json.dumps(body).encode("utf-8")


class Hello:
    """Greets HallPass every EVERY seconds with whatever describe() returns (the keyword arguments of greeting)."""

    def __init__(self, describe, port=PORT):
        self.describe = describe
        self.port = int(port)
        self.stop = threading.Event()
        self.sock = None
        self.thread = None
        self.sent = 0
        self.error = None

    def once(self):
        data = greeting(**self.describe())
        for target in broadcast_targets() + ["127.0.0.1"]:
            try:
                self.sock.sendto(data, (target, self.port))
            except OSError as exc:
                self.error = str(exc)
        self.sent += 1

    def _run(self):
        while not self.stop.is_set():
            try:
                self.once()
            except Exception as exc:          # describe() reads the GUI's state; it must never take the GUI down
                self.error = str(exc)
            self.stop.wait(EVERY)

    def start(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.thread = threading.Thread(target=self._run, daemon=True, name="hallpass-hello")
        self.thread.start()
        return self

    def close(self):
        self.stop.set()
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
