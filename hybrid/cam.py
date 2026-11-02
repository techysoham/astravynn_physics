"""SLSQP collision-avoidance manoeuvre: minimise |dv| s.t. post-burn Pc <= target.
Burn effect on relative position at TCA via Clohessy-Wiltshire (near-circular orbit, short lead)."""
import numpy as np
from scipy.optimize import minimize
from .pc import rtn_basis, rel_covariance, plane_geometry, pc_2d, HBR_KM
MU = 398600.4418

def cw_shift(dv, n, tau):  # dv m/s [R,T,N] -> displacement km at tau s after burn
    dr, dt, dn = np.asarray(dv) / 1000.0
    s, c = np.sin(n * tau), np.cos(n * tau)
    return np.array([dr / n * s + 2 * dt / n * (1 - c),
                     2 * dr / n * (c - 1) + dt / n * (4 * s - 3 * n * tau),
                     dn / n * s])

def optimise(ev, lead_s=5400.0, target=1e-5, dv_max=1.0, hbr=HBR_KM):
    rp, vp, rs, vs = (np.array(ev[k], float) for k in ("rp", "vp", "rs", "vs"))
    B = rtn_basis(rp, vp); n = np.sqrt(MU / np.linalg.norm(rp) ** 3)
    C = rel_covariance(rp, vp, rs, vs, ev.get("agep", 1), ev.get("ages", 1))
    def pc_after(dv):
        shift = B.T @ cw_shift(dv, n, lead_s)
        d, C2 = plane_geometry(rs - (rp + shift), vs - vp, C)
        return pc_2d(d, C2, hbr), d
    pc0, d0 = pc_after(np.zeros(3))
    lt = np.log10(target)
    cons = [{"type": "ineq", "fun": lambda x: lt - np.log10(max(pc_after(x)[0], 1e-300))}]
    best = None
    for x0 in ([0, .05, 0], [0, -.05, 0], [.05, 0, 0], [0, 0, .05], [0, 0, -.05]):
        r = minimize(lambda x: float(np.dot(x, x)), x0, jac=lambda x: 2 * x, method="SLSQP",
                     bounds=[(-dv_max, dv_max)] * 3, constraints=cons, options={"maxiter": 200, "ftol": 1e-12})
        if r.success and pc_after(r.x)[0] <= target * 1.001 and (best is None or r.fun < best.fun):
            best = r
    out = {"pc_before": pc0, "miss_before_km": float(d0), "target": target, "lead_s": lead_s,
           "model": "Clohessy-Wiltshire impulsive burn, optimised by SciPy SLSQP"}
    if pc0 <= target:
        return {**out, "needed": False, "dv_rtn_ms": [0, 0, 0], "dv_ms": 0.0, "pc_after": pc0, "miss_after_km": float(d0)}
    if best is None:
        return {**out, "needed": True, "feasible": False, "note": "No feasible burn within dv_max / lead time"}
    pa, da = pc_after(best.x)
    return {**out, "needed": True, "feasible": True, "dv_rtn_ms": best.x.tolist(),
            "dv_ms": float(np.linalg.norm(best.x)), "pc_after": pa, "miss_after_km": float(da)}
