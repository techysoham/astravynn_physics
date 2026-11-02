"""ASTRAVYNN / AERIS local server. Python 3.8+, no dependencies.
Run:  python server.py   (opens http://localhost:8000)
      python server.py --offline   never touch the network, use catalog_cache.json only
- Fetches CelesTrak at most once every 2 hours (their refresh cycle), cached on disk.
- Compares each new snapshot with the previous one to flag candidate maneuvers
  (same idea as Orbital Radar's Maneuver Tracker: new element set vs its predecessor).
- Proxies the NOAA Kp index (10 min cache)."""
import json, math, os, sys, threading, time, urllib.request, webbrowser
from datetime import datetime, timedelta, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

BASE = "https://celestrak.org/NORAD/elements/gp.php?GROUP={}&FORMAT=tle"
GROUPS = ["active", "cosmos-2251-debris", "iridium-33-debris",
          "fengyun-1c-debris", "cosmos-1408-debris"]
CACHE, EVENTS, TTL = "catalog_cache.json", "maneuvers.json", 2 * 3600
UA = {"User-Agent": "astravynn-student-project"}
OFFLINE = "--offline" in sys.argv or os.environ.get("ASTRAVYNN_OFFLINE") == "1"
FETCH_TIMEOUT = 8      # seconds per request (was 30, and 5 groups in series)
BACKOFF = 600          # after a failed refresh, do not retry for 10 minutes
_fail_until = 0
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
                      "da": round(da, 2), "di": round(di, 4), "dv": round(dv, 2), "sev": sev,
                      "a1": round(a1, 1), "a2": round(a2, 1), "i1": round(i1, 4), "i2": round(i2, 4), "dt": round(dt * 24, 1)})
    return found


def load_cache():
    with open(CACHE) as f:
        return json.load(f)


def refresh():
    """Download all groups. A failed group keeps its previous entries so a partial outage cannot shrink the catalog."""
    old = load_cache() if os.path.exists(CACHE) else {"sats": []}
    sats, seen, failed = [], set(), []
    for g in GROUPS:
        try:
            text = urllib.request.urlopen(urllib.request.Request(BASE.format(g), headers=UA), timeout=FETCH_TIMEOUT).read().decode()
            got = parse(text, g)
            if not got:
                raise ValueError("empty response")
        except Exception as e:
            print("fetch failed", g, e); failed.append(g)
            if not sats and len(failed) >= 2:   # network is down: stop waiting on the remaining groups
                return None
            got = [s for s in old["sats"] if s["g"] == g]
        for s in got:
            k = s["a"][2:7]
            if k not in seen:
                seen.add(k); sats.append(s)
    if len(failed) == len(GROUPS) or not sats:
        return None
    if old["sats"] and not failed:
        ev = json.load(open(EVENTS)) if os.path.exists(EVENTS) else []
        have = {(e["id"], e["t"]) for e in ev}
        ev += [e for e in detect(old["sats"], sats) if (e["id"], e["t"]) not in have]
        cutoff = (time.time() - 30 * 86400) * 1000
        json.dump([e for e in ev if e["t"] > cutoff], open(EVENTS, "w"))
    cat = {"fetched": time.time() if not failed else old.get("fetched", time.time()), "sats": sats}
    json.dump(cat, open(CACHE, "w"))
    return cat


_kp = {"t": 0, "v": None}
def kp():
    if OFFLINE or time.time() - _kp["t"] < 600:
        return _kp["v"]
    _kp["t"] = time.time()
    try:
        d = json.loads(urllib.request.urlopen(urllib.request.Request(
            "https://services.swpc.noaa.gov/json/planetary_k_index_1m.json", headers=UA), timeout=5).read())
        _kp["v"] = d[-1].get("estimated_kp", d[-1].get("kp_index"))
    except Exception as e:
        print("kp failed", e)
    return _kp["v"]


_bg = {"running": False}
def start_bg_refresh():
    global _fail_until
    if _bg["running"]:
        return
    _bg["running"] = True
    def work():
        global _fail_until
        try:
            if not refresh():
                _fail_until = time.time() + BACKOFF
        except Exception as e:
            print("background refresh failed", e); _fail_until = time.time() + BACKOFF
        finally:
            _bg["running"] = False
    threading.Thread(target=work, daemon=True).start()


def get_catalog():
    """Returns the catalog plus provenance: source = live | cache, fetched (unix s), age_h, note."""
    global _fail_until
    have = os.path.exists(CACHE)
    cat = load_cache() if have else None
    note = ""
    source = "cache"
    stale = (not cat) or (time.time() - cat["fetched"] > TTL)
    if stale and not OFFLINE and time.time() >= _fail_until:
        if cat is None:   # nothing cached at all: we have to wait for the first download
            new = refresh()
            if new:
                cat, source = new, "live"
            else:
                _fail_until = time.time() + BACKOFF
                note = "CelesTrak unreachable and no cache."
        else:             # serve the cache NOW, refresh in the background for the next load
            start_bg_refresh()
            note = "Cache is older than 2 h; a fresh download is running in the background. Reload in a minute for fresh TLEs."
    elif stale and OFFLINE:
        note = "Offline mode: serving the cached snapshot."
    elif stale:
        note = "CelesTrak unreachable; serving the last cached snapshot."
    if cat is None:
        cat = {"fetched": 0, "sats": []}
        note = "No cache and no network."
    cat["source"], cat["note"] = source, note
    cat["age_h"] = round((time.time() - cat["fetched"]) / 3600, 2) if cat["fetched"] else None
    cat["maneuvers"] = (json.load(open(EVENTS)) if os.path.exists(EVENTS) else [])[-300:]
    cat["kp"] = kp()
    return json.dumps(cat)


class H(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".js": "application/javascript", ".json": "application/json", ".html": "text/html"}

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def do_GET(self):
        if self.path.startswith("/api/refresh"):
            global _fail_until
            out = {"ok": False, "msg": ""}
            have = os.path.exists(CACHE)
            age = (time.time() - load_cache()["fetched"]) / 60 if have else 1e9
            if OFFLINE:
                out["msg"] = "Server is in offline mode (--offline); no download attempted."
            elif age < 15:
                out["msg"] = "Snapshot is only %.0f min old. CelesTrak updates about every 2 h; try later." % age
            else:
                before = len(json.load(open(EVENTS))) if os.path.exists(EVENTS) else 0
                cat = refresh()
                if cat:
                    after = len(json.load(open(EVENTS))) if os.path.exists(EVENTS) else 0
                    out = {"ok": True, "msg": "Downloaded %d objects; %d new candidate maneuver(s) found." % (len(cat["sats"]), after - before)}
                else:
                    _fail_until = time.time() + BACKOFF
                    out["msg"] = "CelesTrak unreachable; keeping the cached snapshot."
            body = json.dumps(out).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path.startswith("/api/catalog"):
            body = get_catalog().encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            super().do_GET()

    def log_message(self, fmt, *a):
        if "/api/" in (a[0] if a else ""):
            super().log_message(fmt, *a)


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    srv = None
    for port in range(8000, 8010):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", port), H); break
        except OSError:
            print("port", port, "busy, trying next")
    if srv is None:
        sys.exit("No free port in 8000-8009")
    url = "http://localhost:%d" % port
    print("ASTRAVYNN serving on", url, "(OFFLINE: cache only)" if OFFLINE else "")
    if "--no-browser" not in sys.argv:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
