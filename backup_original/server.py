"""Local server for Orbit Watch. Python 3.8+, no dependencies.
Run:  python server.py   then open http://localhost:8000
- Fetches CelesTrak at most once every 2 hours (their refresh cycle), cached on disk.
- Compares each new snapshot with the previous one to flag candidate maneuvers
  (same idea as Orbital Radar's Maneuver Tracker: new element set vs its predecessor).
- Proxies the NOAA Kp index (10 min cache)."""
import json, math, os, time, urllib.request
from datetime import datetime, timedelta, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

BASE = "https://celestrak.org/NORAD/elements/gp.php?GROUP={}&FORMAT=tle"
GROUPS = ["active", "cosmos-2251-debris", "iridium-33-debris",
          "fengyun-1c-debris", "cosmos-1408-debris"]
CACHE, EVENTS, TTL = "catalog_cache.json", "maneuvers.json", 2 * 3600
UA = {"User-Agent": "orbit-watch-student-project"}
MU = 398600.4418
WATCH = {"53323", "51511", "55131", "49330", "41838", "25544", "48274", "20580"}


def parse(text, group):
    lines = [l.rstrip() for l in text.splitlines() if l.strip()]
    out = []
    for i in range(0, len(lines) - 2, 3):
        n, l1, l2 = lines[i], lines[i + 1], lines[i + 2]
        if l1.startswith("1 ") and l2.startswith("2 "):
            out.append({"n": n.strip(), "a": l1, "b": l2, "g": group})
    return out


def elems(s):
    l1, l2 = s["a"], s["b"]
    yr = int(l1[18:20]); yr += 2000 if yr < 57 else 1900
    ep = (datetime(yr, 1, 1, tzinfo=timezone.utc) + timedelta(days=float(l1[20:32]) - 1)).timestamp()
    inc = float(l2[8:16]); n = float(l2[52:63])
    a = (MU / (n * 2 * math.pi / 86400) ** 2) ** (1 / 3)
    return ep, inc, a


def detect(prev, new):
    """Candidate maneuvers from element changes between two snapshots."""
    old = {s["a"][2:7].strip(): s for s in prev}
    found = []
    for s in new:
        nid = s["a"][2:7].strip()
        if nid not in old:
            continue
        try:
            e1, i1, a1 = elems(old[nid]); e2, i2, a2 = elems(s)
        except ValueError:
            continue
        dt = (e2 - e1) / 86400
        if dt < 0.02:
            continue
        da, di = a2 - a1, i2 - i1
        v = math.sqrt(MU / a2) * 1000  # m/s
        kind = dv = None
        if abs(di) > 0.02:
            kind, dv = "Plane Change", 2 * v * math.sin(math.radians(abs(di)) / 2)
        elif da > 1.0:
            kind, dv = "Altitude Raise", v * da / (2 * a2)
        elif da < -(2.0 + dt) and a2 < 8400:
            kind, dv = "Altitude Lower", v * abs(da) / (2 * a2)
        if not kind:
            continue
        sev = "Critical" if nid in WATCH else "High" if kind == "Plane Change" or dv > 20 else "Low"
        found.append({"id": nid, "name": s["n"], "t": int(e2 * 1000), "type": kind,
                      "da": round(da, 2), "di": round(di, 4), "dv": round(dv, 2), "sev": sev})
    return found


def refresh():
    sats, seen = [], set()
    for g in GROUPS:
        try:
            text = urllib.request.urlopen(urllib.request.Request(BASE.format(g), headers=UA), timeout=30).read().decode()
        except Exception as e:
            print("fetch failed", g, e); continue
        for s in parse(text, g):
            k = s["a"][2:7]
            if k not in seen:
                seen.add(k); sats.append(s)
    if not sats:
        return None
    if os.path.exists(CACHE):
        prev = json.load(open(CACHE))["sats"]
        ev = json.load(open(EVENTS)) if os.path.exists(EVENTS) else []
        have = {(e["id"], e["t"]) for e in ev}
        ev += [e for e in detect(prev, sats) if (e["id"], e["t"]) not in have]
        cutoff = (time.time() - 30 * 86400) * 1000
        json.dump([e for e in ev if e["t"] > cutoff], open(EVENTS, "w"))
    cat = {"fetched": time.time(), "sats": sats}
    json.dump(cat, open(CACHE, "w"))
    return cat


_kp = {"t": 0, "v": None}
def kp():
    if time.time() - _kp["t"] < 600:
        return _kp["v"]
    _kp["t"] = time.time()
    try:
        d = json.loads(urllib.request.urlopen(urllib.request.Request(
            "https://services.swpc.noaa.gov/json/planetary_k_index_1m.json", headers=UA), timeout=10).read())
        _kp["v"] = d[-1].get("estimated_kp", d[-1].get("kp_index"))
    except Exception as e:
        print("kp failed", e)
    return _kp["v"]


def get_catalog():
    fresh = os.path.exists(CACHE) and time.time() - os.path.getmtime(CACHE) < TTL
    cat = json.load(open(CACHE)) if fresh else refresh()
    if cat is None:
        cat = json.load(open(CACHE)) if os.path.exists(CACHE) else {"fetched": 0, "sats": []}
    cat["maneuvers"] = (json.load(open(EVENTS)) if os.path.exists(EVENTS) else [])[-300:]
    cat["kp"] = kp()
    return json.dumps(cat)


class H(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/api/catalog"):
            body = get_catalog().encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            super().do_GET()


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    print("Serving on http://localhost:8000")
    ThreadingHTTPServer(("", 8000), H).serve_forever()
