"""Physics: 2D conjunction-plane Probability of Collision (Foster/Chan style).
TLEs carry no covariance, so an ASSUMED RTN covariance grown with TLE age is used (labelled in output)."""
import numpy as np
from scipy.integrate import dblquad

HBR_KM = 0.010  # combined hard-body radius, 10 m (assumption)

def rtn_basis(r, v):
    r, v = np.asarray(r, float), np.asarray(v, float)
    R = r / np.linalg.norm(r); N = np.cross(r, v); N /= np.linalg.norm(N)
    return np.array([R, np.cross(N, R), N])  # rows: R, T, N (inertial components)

def assumed_sigma(age_days):
    """1-sigma RTN position uncertainty (km) vs TLE age. Illustrative, not operational."""
    a = max(float(age_days), 0.0)
    return np.array([0.10 + 0.05 * a, 0.50 + 0.60 * a, 0.10 + 0.05 * a])

def rel_covariance(rp, vp, rs, vs, age_p, age_s):
    Bp, Bs = rtn_basis(rp, vp), rtn_basis(rs, vs)
    Cp = Bp.T @ np.diag(assumed_sigma(age_p) ** 2) @ Bp
    Cs = Bs.T @ np.diag(assumed_sigma(age_s) ** 2) @ Bs
    return Cp + Cs

def plane_geometry(rel_pos, rel_vel, C):
    """Project onto encounter plane (normal = relative velocity). x-axis along miss vector."""
    vh = rel_vel / np.linalg.norm(rel_vel)
    rp = rel_pos - np.dot(rel_pos, vh) * vh
    d = np.linalg.norm(rp)
    u = rp / d if d > 1e-12 else np.cross(vh, [1.0, 0, 0]) / np.linalg.norm(np.cross(vh, [1.0, 0, 0]))
    w = np.cross(vh, u)
    P = np.array([u, w])
    return d, P @ C @ P.T

def pc_2d(d, C2, hbr=HBR_KM, method="fast"):
    """Pc = integral of N(0,C2) over disc radius hbr centred at (d,0)."""
    Ci = np.linalg.inv(C2); k = 1.0 / (2 * np.pi * np.sqrt(np.linalg.det(C2)))
    if method == "dblquad":  # reference method named in the synopsis
        f = lambda y, x: k * np.exp(-0.5 * (np.array([x, y]) @ Ci @ np.array([x, y])))
        val, _ = dblquad(f, d - hbr, d + hbr, lambda x: -np.sqrt(max(hbr**2 - (x - d)**2, 0)),
                         lambda x: np.sqrt(max(hbr**2 - (x - d)**2, 0)), epsabs=1e-16, epsrel=1e-6)
        return float(val)
    n_r, n_t = 24, 48  # fast polar Gauss-style grid (vectorised) for training/optimisation
    rr = (np.arange(n_r) + 0.5) / n_r * hbr; tt = (np.arange(n_t) + 0.5) / n_t * 2 * np.pi
    R, T = np.meshgrid(rr, tt, indexing="ij")
    x, y = d + R * np.cos(T), R * np.sin(T)
    q = Ci[0, 0] * x * x + 2 * Ci[0, 1] * x * y + Ci[1, 1] * y * y
    return float(np.sum(k * np.exp(-0.5 * q) * R) * (hbr / n_r) * (2 * np.pi / n_t))

def assess(ev, hbr=HBR_KM, method="dblquad"):
    rp, vp, rs, vs = (np.array(ev[k], float) for k in ("rp", "vp", "rs", "vs"))
    C = rel_covariance(rp, vp, rs, vs, ev.get("agep", 1), ev.get("ages", 1))
    d, C2 = plane_geometry(rs - rp, vs - vp, C)
    return {"pc": pc_2d(d, C2, hbr, method), "miss_km": d, "C2": C2.tolist(), "hbr_km": hbr,
            "covariance_note": "ASSUMED RTN sigma grows with TLE age (TLEs have no covariance)"}
