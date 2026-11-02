"""Run ONCE while online:  python setup_offline.py
Downloads the 3D/orbit libraries and the Earth texture into ./vendor so the demo works with no internet."""
import os, urllib.request
FILES = {
 "three.min.js": "https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js",
 "OrbitControls.js": "https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js",
 "satellite.min.js": "https://cdn.jsdelivr.net/npm/satellite.js@5.0.0/dist/satellite.min.js",
 "earth.jpg": "https://unpkg.com/three-globe/example/img/earth-blue-marble.jpg",
}
os.makedirs("vendor", exist_ok=True)
for name, url in FILES.items():
    dest = os.path.join("vendor", name)
    try:
        data = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "astravynn"}), timeout=60).read()
        open(dest, "wb").write(data); print("OK  ", name, len(data), "bytes")
    except Exception as e:
        print("FAIL", name, e)
print("Done. Now run: python server.py")
