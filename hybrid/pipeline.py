from . import ml, pc, cam
def run(ev, target=1e-5, lead_s=5400.0, thr=0.3, pc_alert=1e-4):
    """ML gate -> physics Pc -> SLSQP CAM. Physics always runs for audit, but flags show the gated path."""
    s1 = ml.predict(ev, thr)
    s2 = pc.assess(ev)
    out = {"stage1_ml": s1, "stage2_pc": s2, "alert_pc": pc_alert}
    out["decision"] = "BENIGN (logged)" if not s1["high_risk"] and s2["pc"] <= pc_alert else ("CRITICAL: manoeuvre recommended" if s2["pc"] > pc_alert else "MONITOR")
    if s2["pc"] > pc_alert:
        out["stage3_cam"] = cam.optimise(ev, lead_s=lead_s, target=target)
    out["ml_agrees_with_physics"] = s1["high_risk"] == (s2["pc"] > ml.PC_LIMIT)
    return out
