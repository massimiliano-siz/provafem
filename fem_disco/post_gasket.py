"""Pressione di contatto sulla guarnizione EPDM (faccia inferiore disco) e verifica tenuta."""
import sys, json, math
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.tri as mtri
from frd import read_frd

name = sys.argv[1]
P = json.load(open(name + "_info.json"))["P"]
nodes, blocks = read_frd(name + ".frd")
tmax = max(b["time"] for b in blocks)
C = [b for b in blocks if b["name"] == "CONTACT" and abs(b["time"] - tmax) < 1e-6][-1]
ic = C["comps"].index("CPRESS") if "CPRESS" in C["comps"] else 3
xyz = np.array([nodes[n] for n in C["ids"]])
cp = C["vals"][:, ic]
disc = set()
with open(name + ".inp") as f:
    mode = None
    for L in f:
        if L.startswith("*"):
            mode = L.upper().startswith("*ELEMENT") and "ELSET=DISC" in L.upper(); continue
        if mode:
            disc.update(int(v) for v in L.split(",")[1:])
isd = np.array([n in disc for n in C["ids"]])
sel = isd & (np.abs(xyz[:, 2]) < 0.5)   # nodi faccia inferiore disco (guarnizione)
x, y, c = xyz[sel, 0], xyz[sel, 1], cp[sel]
r = np.hypot(x, y); th = np.degrees(np.arctan2(y, x))
p = P["p"]
# minimo lungo la circonferenza per fasce radiali di 2 mm
edges = np.arange(P["Rseal"], P["R"] + 2, 2.0)
rows = []
for a, b in zip(edges[:-1], edges[1:]):
    m = (r >= a) & (r < b)
    if m.sum() > 3:
        rows.append((0.5 * (a + b), c[m].min(), c[m].max()))
rows = np.array(rows)
ok = rows[:, 1] > p
print("p = %.2f MPa" % p)
print("raggio  cp_min(θ)  cp_max(θ) [MPa]")
for rr, mn, mx in rows[::3]:
    print("%6.1f  %8.3f  %8.3f" % (rr, mn, mx))
print("fasce con cp_min > p:", rows[ok, 0].min() if ok.any() else None, "-", rows[ok, 0].max() if ok.any() else None,
      " larghezza tenuta continua ~ %.0f mm" % (2 * ok.sum()))
# mappa a disco intero
A = math.radians(P["ang"]); TH = np.arctan2(y, x)
XS, YS, VS = [], [], []
for k in range(20):
    for s in (1, -1):
        XS.append(r * np.cos(s * TH + 2 * k * A)); YS.append(r * np.sin(s * TH + 2 * k * A)); VS.append(c)
XS, YS, VS = map(np.concatenate, (XS, YS, VS))
fig, ax = plt.subplots(1, 2, figsize=(13, 5.5))
tc = ax[0].tricontourf(XS, YS, VS, levels=np.linspace(0, np.percentile(VS, 99), 21), cmap="viridis", extend="max")
ax[0].tricontour(XS, YS, VS, levels=[p], colors="r", linewidths=1)
plt.colorbar(tc, ax=ax[0], shrink=0.85); ax[0].set_aspect("equal"); ax[0].set_xticks([]); ax[0].set_yticks([])
ax[0].set_title("Pressione di contatto guarnizione [MPa] (rosso = %.1f bar)" % (p * 10), fontsize=10)
ax[1].plot(rows[:, 0], rows[:, 1], label="minimo sulla circonferenza")
ax[1].plot(rows[:, 0], rows[:, 2], label="massimo (sotto bullone)")
ax[1].axhline(p, color="r", lw=0.8, label="pressione fluido")
ax[1].axvline(P["Rb"], color="k", ls=":", lw=0.7)
ax[1].set_xlabel("raggio [mm]"); ax[1].set_ylabel("pressione contatto [MPa]"); ax[1].grid(alpha=0.3); ax[1].legend(fontsize=8)
ax[1].set_title("Pressione sulla guarnizione lungo il raggio", fontsize=10)
fig.suptitle("Disco %.0f mm, guarnizione EPDM 2 mm, %.1f bar" % (P["t"], p * 10))
fig.tight_layout(); fig.savefig(name + "_guarnizione.png", dpi=130)
