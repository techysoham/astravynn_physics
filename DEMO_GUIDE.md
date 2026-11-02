# ASTRAVYNN / AERIS Mission Console: demo guide

## 1. Launch on Windows
Folder contents: `index.html  astra_core.js  screen_worker.js  server.py  catalog_cache.json  vendor\  run.bat  run_offline.bat  setup_offline.py  tests\  backup_original\`

**Tonight (once, with internet):**
```
cd path\to\astravynn
python setup_offline.py      (downloads Three.js, satellite.js, Earth texture into vendor\)
python server.py             (downloads fresh TLEs, caches them, opens the browser)
```
**At the panel (one command, works with no internet):**
```
python server.py --offline       (or double-click run_offline.bat)
```
Then open http://localhost:8000 (opens automatically). Plain `python server.py` also works: if CelesTrak is unreachable it returns in seconds and serves the cache, labelled with its age.
Requires Python 3.8+ only (no pip packages). Use Chrome or Edge.

## 2. Demo checklist (about 6 minutes)
1. **Header badge**: shows `LIVE` or `CACHED TLEs · <timestamp>`. Say which it is. Bottom bar shows object count and Kp.
2. **Live Globe**: rotate/zoom; toggle orbit classes; type `ISS (ZARYA)` in Layers search + Enter. Right panel = altitude, speed, period, TLE age.
3. **Satellite Details** (button "Full details"): elements, lat/lon/alt, raw TLE.
4. **Conjunction Assessment** (button "Screen conjunctions"): set 6 h, 25 km (use 50 km if empty), **Run screening**. Show progress, result table, click a row: TCA, miss, relative speed, RTN components, TLE ages. Open "Calculation assumptions".
5. **Show on globe at TCA**: clock pauses at TCA; the object panel shows *Live separation*, which equals the computed miss distance (cross-check of the calculation).
6. **Risk Analysis**: documented tier criteria, timeline of events, explicit "not a collision probability" notice.
7. **Maneuver Scenario**: banner says SIMULATED. Change direction / Δv / lead time; show miss before vs after and the sweep chart. If the run found no event, press **Create SIMULATED encounter** (synthetic secondary, labelled).
8. **Method & Status**: implemented vs simulated vs planned, data source, library source.
9. **Maneuver Tracker** (new): KPI cards, ΔV-vs-time chart (click a dot), filters (window, type, severity, search, strategic only), detail panel with before/after orbit and an animated orbit-change graphic, and buttons to view the object on the globe or screen its conjunctions. Real detections need two snapshots ≥ 2 h apart: **run `python server.py` online tonight, and again an hour or two later (or press "Refresh data now")**. If the real list is empty on stage, press **Load simulated sample**: it is labelled SIMULATED everywhere.
10. **Animations**: while screening, a rotating 3D shell shows the real candidate objects lighting up as they are screened. In an event, the encounter viewer animates the secondary passing the primary in the RTN frame (drag to rotate, wheel to zoom, scrub the slider; ring radii = tier thresholds). In Maneuver Scenario the viewer shows nominal vs after-burn tracks together. Globe: hover tooltips, pulsing selection, ⟳ Rotate button.

**Rehearse tonight:** run screening for ISS and 2 other objects (e.g. a `FENGYUN 1C DEB`, a Starlink) at 25/50 km, note which give events. Real SGP4 is a few times slower than my sandbox test: expect roughly 10–40 s for a 6 h / 50 km run on ISS. Don't change the primary mid-run.

## 3. Genuinely implemented vs simulated vs planned
**Implemented (real calculation on real data):** CelesTrak TLE ingestion with disk cache and timestamp; SGP4 propagation of ~18.6k objects; 3D globe; selection and element display; conjunction screening (altitude-band prefilter, synchronized 30 s grid, linearised TCA + ternary refinement on true SGP4 distance, miss distance, relative speed, RTN decomposition, TLE-age flag); rule-based miss-distance tiers; backend maneuver-candidate detection (needs 2+ snapshots); JSON export of an event.
**Simulated / illustrative (labelled in UI):** the maneuver what-if (real numerical model of an idealised impulsive burn, not a recommendation); the "Simulated encounter" (synthetic secondary); the one-object offline sample.
**Planned (future work, say so):** probability of collision (needs covariance/CDMs); AI/ML risk ranking (the "AI-assisted" part of AERIS is **not** implemented); optimal maneuver planning (only a 0.1 m/s grid sweep exists); full catalog (Space-Track), higher-fidelity propagation, new-conjunction check after a burn.

## 4. Viva explanation (technical workflow)
1. **Data**: `server.py` pulls TLEs for active satellites and four debris clouds from CelesTrak (max once per 2 h), caches them with a timestamp, and falls back to the cache offline.
2. **Propagation**: the browser converts each TLE to an SGP4 record (satellite.js) and computes position/velocity in the TEME inertial frame; the globe rotates the Earth by GMST.
3. **Screening**: for a chosen primary, objects whose perigee/apogee band does not overlap are dropped. Primary and candidates are propagated on the same 30 s grid for the window. In each step relative motion is linearised to estimate the time of closest approach; promising steps are refined by ternary search on the exact SGP4 separation to give TCA, miss distance, relative velocity, and the miss vector in the primary's radial/along/cross-track frame.
4. **Risk**: tiers (<1, 1–5, 5–10, 10–25 km) are a rule on miss distance, with a flag when a TLE is >3 days old at TCA. It is a screening priority, not a probability: Pc needs covariance, which public TLEs lack.
5. **Maneuver what-if**: take the primary's SGP4 state at burn time, add Δv in a chosen direction, integrate two-body motion with and without the burn (RK4), add the difference to the SGP4 track, and recompute the minimum separation near TCA. Δv = 0 reproduces the screening result exactly. Labelled simulated; no optimization.
6. **Validation**: `node tests/test_core.js` checks the screening against brute force (TCA within 4 ms, same miss), RTN consistency, and burn-model behaviour. The live-separation readout at TCA is a built-in cross-check.
**Honest limits:** TLE accuracy is km-level and degrades with age; point objects; no covariance; catalog is CelesTrak groups, not the full space catalog.
