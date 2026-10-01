"""Esporta superficie del settore + risultati per il visualizzatore 3D (JSON compatto base64)."""
import json, base64, sys
import numpy as np
from frd import read_frd

cases = [  # (file, tempo totale, etichetta)
    ("g25low", 1.0, "Solo precarico"),
    ("g25low", 1.4, "0,2 bar"),
    ("g25low", 2.0, "0,5 bar"),
    ("g25", 2.0, "2 bar"),
]
if len(sys.argv) > 1:
    cases = json.loads(sys.argv[1])
base = cases[0][0]
P = json.load(open(base + "_info.json"))["P"]

# connettivita' disco
E = []
with open(base + ".inp") as f:
    mode = False
    for L in f:
        if L.startswith("*"):
            mode = L.upper().startswith("*ELEMENT") and "ELSET=DISC" in L.upper(); continue
        if mode:
            E.append([int(v) for v in L.split(",")[1:5]])
E = np.array(E)
cnt = {}
for c in E:
    for f in ((0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3)):  # normali verso l'esterno (ordine qualunque, DoubleSide)
        tri = tuple(c[list(f)])
        key = tuple(sorted(tri))
        cnt[key] = None if key in cnt else tri
tris = np.array([t for t in cnt.values() if t is not None])
# togli le facce sui piani di simmetria (interne al disco intero)
_n = {}
with open(base + ".inp") as f:
    on = False
    for L in f:
        if L.startswith("*"):
            on = L.upper().startswith("*NODE") and "PRINT" not in L.upper() and "FILE" not in L.upper(); continue
        if on:
            v = L.split(","); _n[int(v[0])] = (float(v[1]), float(v[2]))
_A = np.radians(P["ang"])
def _onsym(nn):
    x, y = _n[nn]
    return abs(y) < 1e-5 or abs(-np.sin(_A) * x + np.cos(_A) * y) < 1e-5
tris = np.array([t for t in tris if not all(_onsym(v) for v in t)])
nid = np.unique(tris)
loc = {n: i for i, n in enumerate(nid)}
T = np.vectorize(loc.get)(tris).astype(np.uint32)

def b64(a, dt):
    return base64.b64encode(np.ascontiguousarray(a, dtype=dt).tobytes()).decode()

frds = {}
out = {"P": {k: P[k] for k in ("R", "t", "Rb", "rh", "Rseal", "rw_out", "tw", "ang", "F")}, "cases": []}
X0 = None
for fn, t, lab in cases:
    if fn not in frds:
        frds[fn] = read_frd(fn + ".frd")
    nodes, blocks = frds[fn]
    X = np.array([nodes[n] for n in nid])
    if X0 is None:
        X0 = X
    else:
        assert np.abs(X - X0).max() < 1e-6, "mesh diverse tra i run"
    def blk(name):
        return [b for b in blocks if b["name"] == name and abs(b["time"] - t) < 1e-6][-1]
    def get(b, k):
        m = dict(zip(b["ids"], b["vals"]))
        return np.array([m[n][:k] if n in m else [0.0] * k for n in nid])
    U = get(blk("DISP"), 3)
    S = get(blk("STRESS"), 6)
    sx, sy, sz, txy, tyz, tzx = S.T
    vm = np.sqrt(0.5 * ((sx - sy) ** 2 + (sy - sz) ** 2 + (sz - sx) ** 2) + 3 * (txy ** 2 + tyz ** 2 + tzx ** 2))
    C = blk("CONTACT")
    ci = C["comps"].index("CPRESS")
    cm = dict(zip(C["ids"], C["vals"][:, ci]))
    cp = np.array([cm.get(n, 0.0) if abs(nodes[n][2]) < 1e-4 else 0.0 for n in nid])
    # riepilogo
    rr = np.hypot(X[:, 0], X[:, 1]); zz = X[:, 2]
    dw = np.hypot(X[:, 0] - P["Rb"], X[:, 1])
    away = dw > P["rw_out"] + 4
    wz = (np.abs(zz - P["t"]) < 1e-4) & (dw < P["rw_out"] + 1e-3)
    bot = np.abs(zz) < 1e-4
    pp = max(0.0, t - 1.0) * json.load(open(fn + "_info.json"))["P"]["p"]
    band = []
    for a in np.arange(P["Rseal"], P["R"], 2.0):
        m = bot & (rr >= a) & (rr < a + 2)
        if m.sum() > 3 and cp[m].min() > max(pp, 1e-3):
            band.append(a + 1)
    summ = dict(uz_c=float(U[np.argmin(rr + 1e3 * np.abs(zz - P["t"])), 2]),
                vm_plate=float(vm[away].max()),
                F_bolt=float(-np.mean(S[wz, 2]) * np.pi * (P["rw_out"] ** 2 - P["rh"] ** 2) / 1e3) if wz.any() else None,
                p_washer=float(-np.mean(S[wz, 2])) if wz.any() else None,
                lift_in=float(U[bot & (rr < P["Rseal"] + 3), 2].max()),
                seal_r=[min(band), max(band)] if band else None)
    summ["SF"] = 23.0 / summ["vm_plate"]
    pbar = round(max(0.0, t - 1.0) * json.load(open(fn + "_info.json"))["P"]["p"] * 10, 2)
    out["cases"].append(dict(label=lab, p_bar=pbar, U=b64(U, np.float32), vm=b64(vm, np.float32), cp=b64(cp, np.float32), summary=summ))
    print(lab, "uz max %.2f vm max %.1f cp max %.2f" % (U[:, 2].max(), vm.max(), cp.max()))
out["X"] = b64(X0, np.float32)
out["T"] = b64(T, np.uint32)
out["n"] = len(nid)
json.dump(out, open("viewer_data.json", "w"))
html = open("viewer_template.html").read().replace("__DATA__", json.dumps(out))
open("disco_viewer.html", "w").write(html)
print("nodi", len(nid), "triangoli", len(T))
