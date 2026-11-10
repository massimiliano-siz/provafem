"""Esporta la matrice materiale x spessore per il visualizzatore 3D (disco_viewer.html)."""
import json, base64, os, sys
import numpy as np
from frd import read_frd

MATS = {
    "hdpe": dict(label="HDPE", crit="vm", lim=23.0, limlabel="snervamento", critlabel="von Mises",
                 note="HDPE: E = 1000 MPa, snervamento 23 MPa (duttile, criterio von Mises)."),
    "pmma": dict(label="PMMA (Xometry)", crit="s1", lim=55.0, limlabel="rottura a trazione",
                 critlabel="Tensione principale",
                 note="Acrilico PMMA, dati Xometry: E 2,4–3,4 GPa (usato 3,0), rottura a trazione 55–76 MPa "
                      "(usato il minimo, 55). Fragile: criterio sulla tensione principale massima."),
}
CASES = [(1.0, "Solo precarico"), (1.1, "0,2 bar"), (1.25, "0,5 bar"), (2.0, "2 bar")]
THK = [10, 15, 20, 25]


def b64(a, dt):
    return base64.b64encode(np.ascontiguousarray(a, dtype=dt).tobytes()).decode()


def export(name, mat):
    P = json.load(open(name + "_info.json"))["P"]
    A = np.radians(P["ang"])
    E, Xn = [], {}
    with open(name + ".inp") as f:
        mode = None
        for L in f:
            if L.startswith("*"):
                U_ = L.upper()
                mode = "E" if U_.startswith("*ELEMENT") and "ELSET=DISC" in U_ else (
                    "N" if U_.startswith("*NODE") and "PRINT" not in U_ and "FILE" not in U_ else None)
                continue
            if mode == "E":
                E.append([int(v) for v in L.split(",")[1:5]])
            elif mode == "N":
                v = L.split(",")
                Xn[int(v[0])] = (float(v[1]), float(v[2]))
    cnt = {}
    for c in E:
        for f in ((0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3)):
            tri = (c[f[0]], c[f[1]], c[f[2]])
            key = tuple(sorted(tri))
            cnt[key] = None if key in cnt else tri
    p0 = lambda nn: abs(Xn[nn][1]) < 1e-5
    p1 = lambda nn: abs(-np.sin(A) * Xn[nn][0] + np.cos(A) * Xn[nn][1]) < 1e-5
    tris = np.array([t for t in cnt.values() if t is not None
                     and not (all(p0(v) for v in t) or all(p1(v) for v in t))])
    nid = np.unique(tris)
    loc = {n: i for i, n in enumerate(nid)}
    T = np.vectorize(loc.get)(tris).astype(np.uint32)

    nodes, blocks = read_frd(name + ".frd")
    X = np.array([nodes[n] for n in nid])
    rr = np.hypot(X[:, 0], X[:, 1]); zz = X[:, 2]
    dw = np.hypot(X[:, 0] - P["Rb"], X[:, 1])
    away = dw > P["rw_out"] + 4
    wz = (np.abs(zz - P["t"]) < 1e-4) & (dw < P["rw_out"] + 1e-3)
    bot = np.abs(zz) < 1e-4
    hole_in = P["Rb"] - P["rh"]
    out_cases = []
    for t, lab in CASES:
        bl = {b["name"]: b for b in blocks if abs(b["time"] - t) < 1e-6}
        if not {"DISP", "STRESS", "CONTACT"} <= set(bl):
            continue

        def get(b, k):
            m = dict(zip(b["ids"], b["vals"]))
            return np.array([m[n][:k] if n in m else [0.0] * k for n in nid])
        U = get(bl["DISP"], 3)
        S = get(bl["STRESS"], 6)
        sx, sy, sz, txy, tyz, tzx = S.T
        vm = np.sqrt(0.5 * ((sx - sy) ** 2 + (sy - sz) ** 2 + (sz - sx) ** 2) + 3 * (txy ** 2 + tyz ** 2 + tzx ** 2))
        M = np.stack([np.stack([sx, txy, tzx], -1), np.stack([txy, sy, tyz], -1), np.stack([tzx, tyz, sz], -1)], -2)
        s1 = np.linalg.eigvalsh(M)[:, -1]
        C = bl["CONTACT"]
        ci = C["comps"].index("CPRESS")
        cm = dict(zip(C["ids"], C["vals"][:, ci]))
        cp = np.array([cm.get(n, 0.0) if abs(nodes[n][2]) < 1e-4 else 0.0 for n in nid])
        pp = max(0.0, t - 1.0) * P["p"]
        band = []
        for a in np.arange(P["Rseal"], P["R"], 2.0):
            m = bot & (rr >= a) & (rr < a + 2)
            if m.sum() > 3 and cp[m].min() > max(pp, 1e-3):
                band.append(a + 1)
        runs = []
        for b_ in band:
            if runs and abs(b_ - runs[-1][1] - 2) < 1e-6:
                runs[-1][1] = b_
            else:
                runs.append([b_, b_])
        runs = [[a - 1, b_ + 1] for a, b_ in runs]
        inner = [r_ for r_ in runs if r_[0] < hole_in]
        crit = vm if MATS[mat]["crit"] == "vm" else s1
        s = dict(uz_c=float(U[np.argmin(rr + 1e3 * np.abs(zz - P["t"])), 2]),
                 lift_in=float(U[bot & (rr > P["Rseal"] - 0.5) & (rr < P["Rseal"] + 3), 2].max()),
                 crit_plate=float(crit[away].max()),
                 F_bolt=float(-np.mean(S[wz, 2]) * np.pi * (P["rw_out"] ** 2 - P["rh"] ** 2) / 1e3),
                 p_washer=float(-np.mean(S[wz, 2])),
                 seal_r=[inner[0][0], hole_in] if inner else None)
        s["SF"] = MATS[mat]["lim"] / s["crit_plate"]
        out_cases.append(dict(label=lab, p_bar=round(pp * 10, 2), U=b64(U, np.float32), vm=b64(vm, np.float32),
                              s1=b64(s1, np.float32), cp=b64(cp, np.float32), summary=s))
        print("%-7s %-15s uz_c %6.2f  crit %5.1f  SF %5.2f  seal %s" % (name, lab, s["uz_c"], s["crit_plate"], s["SF"], s["seal_r"]))
    keep = ("R", "t", "Rb", "rh", "Rseal", "rw_out", "tw", "ang", "F")
    return dict(mat=mat, t=int(P["t"]), P={k: P[k] for k in keep}, X=b64(X, np.float32), T=b64(T, np.uint32),
                n=len(nid), cases=out_cases)


configs = {}
for mat in MATS:
    for t in THK:
        name = "%s%d" % (mat, t)
        if os.path.exists(name + ".frd") and os.path.getsize(name + ".frd") > 0:
            c = export(name, mat)
            if c["cases"]:
                configs[name] = c
mats = {k: v for k, v in MATS.items() if any(c["mat"] == k for c in configs.values())}
data = dict(mats=mats, configs=configs)
html = open("viewer_template.html").read().replace("__DATA__", json.dumps(data))
open("disco_viewer.html", "w").write(html)
print("configurazioni:", list(configs), " dimensione html %.1f MB" % (len(html) / 1e6))
