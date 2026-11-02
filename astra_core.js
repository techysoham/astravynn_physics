/* ASTRAVYNN core orbital logic. Pure functions, no DOM. Used by the page, the screening worker and Node tests.
   Everything here is a real calculation; assumptions are documented in the UI (Method & Status). */
(function (root) {
'use strict';
const MU = 398600.4418, RE = 6378.137;

// Screening tiers: based ONLY on predicted miss distance. NOT a probability of collision.
const TIERS = [
  { k: 'Critical', c: '#ff5d6c', lt: 1,        rule: 'miss distance < 1 km' },
  { k: 'High',     c: '#ff8a4c', lt: 5,        rule: '1 km ≤ miss < 5 km' },
  { k: 'Elevated', c: '#f5b942', lt: 10,       rule: '5 km ≤ miss < 10 km' },
  { k: 'Watch',    c: '#4fd1c5', lt: 25,       rule: '10 km ≤ miss < 25 km' },
  { k: 'Info',     c: '#7f90a8', lt: Infinity, rule: 'miss ≥ 25 km (only listed if screening threshold is larger)' }
];
const AGE_LIMIT_DAYS = 3; // TLE older than this at TCA => "low confidence" flag
const tierOf = m => TIERS.find(t => m < t.lt);

const st = (sat, rec, t) => { try { const pv = sat.propagate(rec, new Date(t)); return pv && pv.position && pv.velocity && isFinite(pv.position.x) ? pv : null; } catch (e) { return null; } };
const arr = p => [p.x, p.y, p.z];

/* Close-approach screening of ONE primary against many candidates over [t0, t0+hours].
   Method: both objects are propagated with SGP4 on the SAME time grid (step s). For each step the relative
   motion is linearised to find the time of closest approach (TCA) inside the step; steps whose linear miss is
   below thr+40 km become candidates; each candidate TCA is then refined by ternary search on the true SGP4
   distance. Events with refined miss <= thr are kept. */
function screen(sat, pTle, cands, t0, hours, step, thr, progress) {
  const n = Math.floor(hours * 3600 / step), sp = sat.twoline2satrec(pTle[0], pTle[1]), tEnd = t0 + hours * 3600000, LIM = thr + 40;
  const PA = []; for (let k = 0; k <= n; k++) PA.push(st(sat, sp, t0 + k * step * 1000));
  const res = [];
  for (let j = 0; j < cands.length; j++) {
    const rec = sat.twoline2satrec(cands[j][0], cands[j][1]); if (rec.error) continue;
    const found = [];
    for (let k = 0; k <= n; k++) {
      const a = PA[k]; if (!a) continue; const t = t0 + k * step * 1000, b = st(sat, rec, t); if (!b) continue;
      const rx = b.position.x - a.position.x, ry = b.position.y - a.position.y, rz = b.position.z - a.position.z;
      const vx = b.velocity.x - a.velocity.x, vy = b.velocity.y - a.velocity.y, vz = b.velocity.z - a.velocity.z;
      const v2 = vx * vx + vy * vy + vz * vz; if (v2 < 1e-12) continue;
      const rv = rx * vx + ry * vy + rz * vz, tau = -rv / v2;
      if (tau < -step * 0.5 || tau > step * 1.5) continue;
      if (rx * rx + ry * ry + rz * rz - rv * rv / v2 > LIM * LIM) continue;
      found.push(t + tau * 1000);
    }
    let last = -1e18;
    for (const tg of found) {
      if (tg - last < 120000) continue; last = tg;
      let lo = tg - step * 1000, hi = tg + step * 1000;
      const f = t => { const A = st(sat, sp, t), B = st(sat, rec, t); return A && B ? Math.hypot(B.position.x - A.position.x, B.position.y - A.position.y, B.position.z - A.position.z) : 1e9; };
      for (let it = 0; it < 40; it++) { const m1 = lo + (hi - lo) / 3, m2 = hi - (hi - lo) / 3; if (f(m1) < f(m2)) hi = m2; else lo = m1; }
      const tc = (lo + hi) / 2; if (tc < t0 || tc > tEnd) continue;
      const A = st(sat, sp, tc), B = st(sat, rec, tc); if (!A || !B) continue;
      const miss = Math.hypot(B.position.x - A.position.x, B.position.y - A.position.y, B.position.z - A.position.z);
      if (miss > thr) continue;
      res.push({ j, tca: tc, miss, rv: Math.hypot(B.velocity.x - A.velocity.x, B.velocity.y - A.velocity.y, B.velocity.z - A.velocity.z),
                 rp: arr(A.position), vp: arr(A.velocity), rs: arr(B.position), vs: arr(B.velocity) });
    }
    if (progress && j % 50 === 0) progress(j / cands.length);
  }
  return res;
}

// ---- small vector helpers
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const norm = a => Math.hypot(a[0], a[1], a[2]);
const unit = a => { const n = norm(a); return [a[0] / n, a[1] / n, a[2] / n]; };
const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];

/* Miss vector (secondary - primary) at TCA in the primary's RTN frame (R radial, T along-track, N orbit-normal). */
function rtn(rp, vp, rs, vs) {
  const R = unit(rp), N = unit(cross(rp, vp)), T = cross(N, R), dr = sub(rs, rp), dv = sub(vs, vp);
  return { R: dot(dr, R), T: dot(dr, T), N: dot(dr, N), vR: dot(dv, R), vT: dot(dv, T), vN: dot(dv, N) };
}

/* Osculating elements summary from a TEME state (km, km/s). */
function orbitOf(r, v) {
  const rn = norm(r), v2 = dot(v, v), a = 1 / (2 / rn - v2 / MU), h = cross(r, v);
  const ev = sub(cross(v, h).map(x => x / MU), r.map(x => x / rn)), e = norm(ev);
  return { a, e, rp: a * (1 - e) - RE, ra: a * (1 + e) - RE, period: 2 * Math.PI * Math.sqrt(a * a * a / MU) / 60 };
}

// ---- two-body propagation (RK4) used ONLY to compute the displacement caused by a burn
function rk4(s, h) {
  const f = x => { const k = -MU / Math.pow(x[0] * x[0] + x[1] * x[1] + x[2] * x[2], 1.5); return [x[3], x[4], x[5], x[0] * k, x[1] * k, x[2] * k]; };
  const add = (x, d, c) => x.map((v, i) => v + d[i] * c);
  const k1 = f(s), k2 = f(add(s, k1, h / 2)), k3 = f(add(s, k2, h / 2)), k4 = f(add(s, k3, h));
  return s.map((v, i) => v + h / 6 * (k1[i] + 2 * k2[i] + 2 * k3[i] + k4[i]));
}
function adv(s, T, hMax) { if (T === 0) return s; const n = Math.max(1, Math.ceil(Math.abs(T) / hMax)), h = T / n; for (let i = 0; i < n; i++) s = rk4(s, h); return s; }

/* What-if burn. o: { r, v (primary SGP4 state at burn time), leadS (burn is leadS before nominal TCA),
   offs (seconds relative to nominal TCA, ascending), P, S (SGP4 positions of primary/secondary at those offsets),
   dvMs, axis 'V'|'R'|'N', sign +1|-1 }.
   Primary after burn is modelled as  SGP4(t) + [twoBody(burned) - twoBody(unburned)](t)  so dv=0 reproduces the nominal miss exactly.
   Returns minimum separation (segment-interpolated on the 1 s grid), its time offset, and orbit before/after. */
function evalBurn(o) {
  const ax = { V: unit(o.v), R: unit(o.r), N: unit(cross(o.r, o.v)) }[o.axis], dv = o.dvMs / 1000 * o.sign;
  const v2 = [o.v[0] + ax[0] * dv, o.v[1] + ax[1] * dv, o.v[2] + ax[2] * dv];
  let nS = o.r.concat(o.v), bS = o.r.concat(v2), cur = 0, prev = null, best = { miss: Infinity, off: 0 };
  const relArr = [];
  for (let k = 0; k < o.offs.length; k++) {
    const T = o.leadS + o.offs[k]; nS = adv(nS, T - cur, 10); bS = adv(bS, T - cur, 10); cur = T;
    const rel = [o.S[k][0] - (o.P[k][0] + bS[0] - nS[0]), o.S[k][1] - (o.P[k][1] + bS[1] - nS[1]), o.S[k][2] - (o.P[k][2] + bS[2] - nS[2])];
    if (o.keep) relArr.push(rel);
    if (prev) { // closest point of the segment prev->rel to the origin
      const d = sub(rel, prev), dd = dot(d, d), u = dd > 0 ? Math.max(0, Math.min(1, -dot(prev, d) / dd)) : 0;
      const m = norm([prev[0] + d[0] * u, prev[1] + d[1] * u, prev[2] + d[2] * u]);
      if (m < best.miss) best = { miss: m, off: o.offs[k - 1] + u * (o.offs[k] - o.offs[k - 1]) };
    }
    prev = rel;
  }
  if (o.keep) best.rel = relArr;
  best.edge = Math.abs(best.off) > (o.offs[o.offs.length - 1] - 2);
  best.before = orbitOf(o.r, o.v); best.after = orbitOf(o.r, v2);
  return best;
}

const api = { MU, RE, TIERS, AGE_LIMIT_DAYS, tierOf, screen, rtn, orbitOf, evalBurn, norm, cross, dot, unit };
if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.ASTRA = api;
})(typeof self !== 'undefined' ? self : this);
