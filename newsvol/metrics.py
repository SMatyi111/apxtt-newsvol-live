"""Loss functions and the HAC Diebold-Mariano t (copied from product_check/scripts/compare.py)."""
import numpy as np


def nw_t(d, lag):
    d = np.asarray(d, float)
    d = d[np.isfinite(d)]
    n = len(d)
    if n < 10:
        return float("nan")
    e = d - d.mean()
    s = e @ e / n
    for k in range(1, min(lag, n - 1) + 1):
        s += 2 * (1 - k / (lag + 1)) * (e[k:] @ e[:-k]) / n
    if s <= 0:
        return float("nan")
    return float(d.mean() / np.sqrt(s / n))


def losses(y_bp, f_bp, pipconv):
    """Per-observation losses. y_bp, f_bp: realised and forecast range in bp (1e4 ln(H/L)); pipconv: bp -> pips."""
    y_bp, f_bp, pipconv = (np.asarray(a, float) for a in (y_bp, f_bp, pipconv))
    ly, lf = np.log(y_bp), np.log(f_bp)
    r = np.exp(2 * (ly - lf))
    return {"mse_log": (ly - lf) ** 2, "qlike": r - np.log(r) - 1,
            "mae_pips": np.abs(f_bp - y_bp) * pipconv, "hit25": (np.abs(f_bp / y_bp - 1) <= 0.25).astype(float)}
