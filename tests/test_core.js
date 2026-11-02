// Logic test for astra_core.js using a Kepler two-body stand-in for SGP4 (the real satellite.js is exercised in the browser).
// Verifies: screening finds the same TCA/miss as brute force, RTN decomposition is consistent, a burn with dv=0 reproduces the nominal miss,
// and a prograde burn changes the miss in the expected direction.
const AC = require('../astra_core.js'), MU = AC.MU;
const EP = Date.UTC(2026, 9, 16, 12, 0, 0);
function tle(inc, raan, ecc, argp, M, n) {
  const l2 = '2 99999 ' + inc.toFixed(4).padStart(8) + ' ' + raan.toFixed(4).padStart(8) + ' ' + String(Math.round(ecc * 1e7)).padStart(7, '0') + ' ' + argp.toFixed(4).padStart(8) + ' ' + M.toFixed(4).padStart(8) + ' ' + n.toFixed(8).padStart(11) + '    1';
  return ['1 99999U 26001A   26289.50000000  .00000000  00000-0  00000-0 0  9990', l2];
}
const sat = {
  twoline2satrec(a, b) { return { inc: +b.slice(8, 16) * Math.PI / 180, raan: +b.slice(17, 25) * Math.PI / 180, e: +('0.' + b.slice(26, 33)), w: +b.slice(34, 42) * Math.PI / 180, M0: +b.slice(43, 51) * Math.PI / 180, n: +b.slice(52, 63) * 2 * Math.PI / 86400 }; },
  propagate(r, d) {
    const dt = (d.getTime() - EP) / 1000, a = Math.cbrt(MU / (r.n * r.n)); let M = r.M0 + r.n * dt, E = M; for (let i = 0; i < 20; i++) E = M + r.e * Math.sin(E);
    const nu = 2 * Math.atan2(Math.sqrt(1 + r.e) * Math.sin(E / 2), Math.sqrt(1 - r.e) * Math.cos(E / 2)), rr = a * (1 - r.e * Math.cos(E)), p = a * (1 - r.e * r.e);
    const xp = rr * Math.cos(nu), yp = rr * Math.sin(nu), vx = -Math.sqrt(MU / p) * Math.sin(nu), vy = Math.sqrt(MU / p) * (r.e + Math.cos(nu));
    const cw = Math.cos(r.w), sw = Math.sin(r.w), co = Math.cos(r.raan), so = Math.sin(r.raan), ci = Math.cos(r.inc), si = Math.sin(r.inc);
    const rot = (x, y) => ({ x: (co * cw - so * sw * ci) * x + (-co * sw - so * cw * ci) * y, y: (so * cw + co * sw * ci) * x + (-so * sw + co * cw * ci) * y, z: (sw * si) * x + (cw * si) * y });
    return { position: rot(xp, yp), velocity: rot(vx, vy) };
  }
};
const nRev = 15.2, T0 = EP + 600000, HRS = 6;
const prim = tle(51.6, 40, 0.0001, 0, 0, nRev), pr = sat.twoline2satrec(...prim);
const d = (a, b, t) => { const A = sat.propagate(a, new Date(t)).position, B = sat.propagate(b, new Date(t)).position; return Math.hypot(A.x - B.x, A.y - B.y, A.z - B.z); };
// find a secondary phasing that produces a 1-20 km approach inside the window (coarse scan, then fine brute force)
let best = null;
for (let M = 0; M < 360 && !best; M += 0.25) {
  const sd = tle(98, 130, 0.0001, 0, M, nRev), sr = sat.twoline2satrec(...sd); let mn = 1e9, tm = 0;
  for (let t = T0; t < T0 + HRS * 3600e3; t += 5000) { const x = d(pr, sr, t); if (x < mn) { mn = x; tm = t } }
  if (mn < 150) { let m2 = 1e9, t2 = 0; for (let t = tm - 8000; t < tm + 8000; t += 20) { const x = d(pr, sr, t); if (x < m2) { m2 = x; t2 = t } } if (m2 > 0.5 && m2 < 25) best = { sd, sr, miss: m2, t: t2 } }
}
if (!best) { console.log('no suitable synthetic encounter found'); process.exit(2) }
const ev = AC.screen(sat, prim, [best.sd], T0, HRS, 30, 50, null);
let fails = 0; const chk = (n, c, x) => { console.log((c ? 'PASS ' : 'FAIL ') + n + (x ? '  ' + x : '')); if (!c) fails++ };
ev.sort((a, b) => Math.abs(a.tca - best.t) - Math.abs(b.tca - best.t)); const e = ev[0];
chk('screening reproduces the brute-force encounter (nearest event)', ev.length >= 1 && Math.abs(e.tca - best.t) < 1500 && Math.abs(e.miss - best.miss) < 0.6,
    e ? `${ev.length} event(s) listed; TCA diff ${(e.tca - best.t).toFixed(0)} ms, miss ${e.miss.toFixed(3)} km vs brute ${best.miss.toFixed(3)} km, rel speed ${e.rv.toFixed(2)} km/s` : 'none');
const q = AC.rtn(e.rp, e.vp, e.rs, e.vs);
chk('RTN components reproduce miss distance', Math.abs(Math.hypot(q.R, q.T, q.N) - e.miss) < 1e-6);
chk('tier assignment', AC.tierOf(0.5).k === 'Critical' && AC.tierOf(3).k === 'High' && AC.tierOf(7).k === 'Elevated' && AC.tierOf(12).k === 'Watch' && AC.tierOf(40).k === 'Info');
const far = AC.screen(sat, prim, [tle(51.6, 40, 0.0001, 0, 180, nRev)], T0, HRS, 30, 50, null);
chk('co-orbital object 180° away yields no event', far.length === 0);
// maneuver what-if
const leadS = 3600, tb = e.tca - leadS * 1000, pb = sat.propagate(pr, new Date(tb)), sr = best.sr, offs = [], Pp = [], Ss = [];
for (let k = -120; k <= 120; k++) { offs.push(k); const a = sat.propagate(pr, new Date(e.tca + k * 1000)).position, b = sat.propagate(sr, new Date(e.tca + k * 1000)).position; Pp.push([a.x, a.y, a.z]); Ss.push([b.x, b.y, b.z]) }
const base = { r: [pb.position.x, pb.position.y, pb.position.z], v: [pb.velocity.x, pb.velocity.y, pb.velocity.z], leadS, offs, P: Pp, S: Ss };
const b0 = AC.evalBurn({ ...base, dvMs: 0, axis: 'V', sign: 1 });
chk('dv=0 reproduces nominal miss (1 s grid, interpolated)', Math.abs(b0.miss - e.miss) < 0.05, `${b0.miss.toFixed(3)} vs ${e.miss.toFixed(3)} km`);
const b1 = AC.evalBurn({ ...base, dvMs: 1, axis: 'V', sign: 1 }), b2 = AC.evalBurn({ ...base, dvMs: 2, axis: 'V', sign: 1 });
// prograde burn 1 h (≈0.67 orbit) before TCA: along-track shift ≈ 3*dv*dt-ish ⇒ several km
chk('1 m/s prograde burn moves the miss by several km', Math.abs(b1.miss - b0.miss) > 2, `miss ${b0.miss.toFixed(2)} -> ${b1.miss.toFixed(2)} km`);
const b3 = AC.evalBurn({ ...base, dvMs: 1.05, axis: 'V', sign: 1 });
chk('result is continuous in dv (1.00 vs 1.05 m/s differ < 1.5 km) and 2 m/s also changes miss', Math.abs(b3.miss - b1.miss) < 1.5 && Math.abs(b2.miss - b0.miss) > 2, `1.05 m/s: ${b3.miss.toFixed(2)}, 2 m/s: ${b2.miss.toFixed(2)} km`);
chk('post-burn apogee rises for prograde burn', b1.after.ra > b1.before.ra && Math.abs(b1.before.a - Math.cbrt(MU / Math.pow(nRev * 2 * Math.PI / 86400, 2))) < 1);
console.log(fails ? fails + ' FAILED' : 'ALL PASSED'); process.exit(fails ? 1 : 0);
