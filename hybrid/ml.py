"""ML pre-screen. XGBoost if installed, else sklearn HistGradientBoosting (same role).
Trained on physics-labelled SYNTHETIC encounters (label = Pc > 1e-4 from pc.py). Honest limit stated in metrics."""
import json, os, time
import numpy as np
from .pc import rtn_basis, rel_covariance, plane_geometry, pc_2d
HERE = os.path.dirname(os.path.abspath(__file__)); MODEL = os.path.join(HERE, "model.joblib"); METRICS = os.path.join(HERE, "model_metrics.json")
PC_LIMIT = 1e-4
_CACHE = None
THR = 0.3  # operating threshold, low to favour recall on the rare high-risk class
FEATS = ["miss", "rv", "mR", "mT", "mN", "agep", "ages", "alt", "cosang"]

def features(ev):
    rp, vp, rs, vs = (np.array(ev[k], float) for k in ("rp", "vp", "rs", "vs"))
    B = rtn_basis(rp, vp); m = B @ (rs - rp)
    cosang = float(np.dot(vp, vs) / (np.linalg.norm(vp) * np.linalg.norm(vs)))
    return [float(np.linalg.norm(rs - rp)), float(np.linalg.norm(vs - vp)), *m.tolist(),
            float(ev.get("agep", 1)), float(ev.get("ages", 1)), float(np.linalg.norm(rp) - 6371.0), cosang]

def _rot(axis, ang):
    a = axis / np.linalg.norm(axis); K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + np.sin(ang) * K + (1 - np.cos(ang)) * K @ K

def synth(rng):
    a = 6371 + rng.uniform(400, 1200); v = np.sqrt(398600.4418 / a)
    rp = np.array([a, 0, 0.]); vp = np.array([0, v, 0.])
    th = rng.uniform(0.25, np.pi); ax = rng.normal(size=3)
    vs = _rot(ax, th) @ vp
    vrel = vs - vp; vh = vrel / np.linalg.norm(vrel)
    u = np.cross(vh, rng.normal(size=3)); u /= np.linalg.norm(u)
    miss = 10 ** rng.uniform(np.log10(0.005), np.log10(8))
    rs = rp + miss * u
    return {"rp": rp, "vp": vp, "rs": rs, "vs": vs, "agep": rng.uniform(0, 10), "ages": rng.uniform(0, 10)}

def label(ev):
    C = rel_covariance(ev["rp"], ev["vp"], ev["rs"], ev["vs"], ev["agep"], ev["ages"])
    d, C2 = plane_geometry(ev["rs"] - ev["rp"], ev["vs"] - ev["vp"], C)
    return pc_2d(d, C2)

def _models():
    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    try:
        from xgboost import XGBClassifier
        main = ("XGBoost", XGBClassifier(n_estimators=300, max_depth=5, learning_rate=0.08, eval_metric="logloss"))
    except Exception:
        main = ("XGBoost-equivalent (sklearn HistGradientBoosting; install xgboost to switch)",
                HistGradientBoostingClassifier(max_iter=300, learning_rate=0.08, class_weight="balanced", random_state=0))
    return [main, ("Logistic Regression", make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, class_weight="balanced"))),
            ("Random Forest", RandomForestClassifier(200, class_weight="balanced", n_jobs=-1, random_state=0))]

def train(n=8000, seed=0):
    import joblib
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score, recall_score, f1_score, roc_auc_score
    rng = np.random.default_rng(seed); X, y = [], []
    for _ in range(n):
        e = synth(rng); X.append(features(e)); y.append(int(label(e) > PC_LIMIT))
    X, y = np.array(X), np.array(y)
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, stratify=y, random_state=seed)
    table, main = [], None
    for i, (name, m) in enumerate(_models()):
        t = time.time(); m.fit(Xtr, ytr); p = m.predict_proba(Xte)[:, 1]; yh = (p > THR).astype(int)
        table.append({"algorithm": name, "accuracy": round(accuracy_score(yte, yh), 3), "recall_high_risk": round(recall_score(yte, yh), 3),
                      "f1": round(f1_score(yte, yh), 3), "roc_auc": round(roc_auc_score(yte, p), 3), "fit_s": round(time.time() - t, 2)})
        if i == 0: main = m
    global _CACHE; _CACHE = main
    try: joblib.dump(main, MODEL)
    except Exception: pass
    out = {"n_samples": n, "positive_rate": float(y.mean()), "pc_limit": PC_LIMIT, "features": FEATS, "table": table,
           "note": "Labels come from the physics Pc on SYNTHETIC encounters with ASSUMED covariance; not validated on real CDMs."}
    json.dump(out, open(METRICS, "w"), indent=2); return out

def predict(ev, thr=THR):
    import joblib
    global _CACHE
    if _CACHE is None:
        try: _CACHE = joblib.load(MODEL)
        except Exception: train()  # missing or built with another scikit-learn version: retrain here (~5 s)
    m = _CACHE; p = float(m.predict_proba([features(ev)])[0, 1])
    return {"p_high_risk": p, "threshold": thr, "high_risk": p > thr, "features": dict(zip(FEATS, features(ev)))}
