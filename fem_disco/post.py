"""Post-processing risultati DiscoPCU."""
import sys, json, math
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.tri as mtri
from frd import read_frd

name = sys.argv[1] if len(sys.argv) > 1 else "disco"
info = json.load(open(name + "_info.json"))
P = info["P"]
SY = float(sys.argv[2]) if len(sys.argv) > 2 else 23.0   # snervamento HDPE [MPa]
nodes, blocks = read_frd(name + ".frd")
ids = np.array(sorted(nodes))
XYZ = np.array([nodes[i] for i in ids])
idx = {n: k for k, n in enumerate(ids)}

# nodi del disco: z in [0, t] e non della rondella/flangia -> uso connettivita' dall'inp
disc_nodes = set()
with open(name + ".inp") as f:
    mode = None
    for L in f:
        if L.startswith("*"):
            mode = "D" if L.upper().startswith("*ELEMENT") and "ELSET=DISC" in L.upper() else None
            continue
        if mode == "D":
            disc_nodes.update(int(v) for v in L.split(",")[1:])
D = np.array(sorted(disc_nodes))
Di = np.array([idx[n] for n in D])
xyz = XYZ[Di]
r = np.hypot(xyz[:, 0], xyz[:, 1])
z = xyz[:, 2]


def field(nm, t, step):
    for b in blocks:
        if b["name"] == nm and abs(b["time"] - t) < 1e-6 and b["step"] == step:
            return b
    return None


def nodal(b, n_list, ncomp):
    m = {i: v for i, v in zip(b["ids"], b["vals"])}
    return np.array([m.get(n, [np.nan] * ncomp)[:ncomp] for n in n_list])


def vm(s):
    sx, sy, sz, txy, tyz, tzx = s.T
    return np.sqrt(0.5 * ((sx - sy) ** 2 + (sy - sz) ** 2 + (sz - sx) ** 2) + 3 * (txy ** 2 + tyz ** 2 + tzx ** 2))


def principal(s):
    out = []
    for sx, sy, sz, txy, tyz, tzx in s:
        out.append(np.linalg.eigvalsh(np.array([[sx, txy, tzx], [txy, sy, tyz], [tzx, tyz, sz]])))
    return np.array(out)


steps = sorted({(b["step"], b["time"]) for b in blocks if b["name"] == "DISP"})
print("output disponibili:", steps)
res = []
for st, t in steps:
    U = nodal(field("DISP", t, st), D, 3)
    S = nodal(field("STRESS", t, st), D, 6)
    sv = vm(S)
    pr = principal(S)
    pbar = 0.0 if st == 1 else P["p"] * t * 10
    bot = np.abs(z) < 1e-4
    top = np.abs(z - P["t"]) < 1e-4
    # sollevamento in corrispondenza dell'O-ring (fondo disco, R 203.5-208.5)
    oring = bot & (r > 203.4) & (r < 208.6)
    # zona rondella (faccia superiore)
    dw = np.hypot(xyz[:, 0] - P["Rb"], xyz[:, 1])
    wz = top & (dw < P["rw_out"] + 1e-3)
    # esclusione zona rondella per tensioni "di piastra"
    away = dw > P["rw_out"] + 4
    k = np.nanargmax(sv)
    ka = np.nanargmax(np.where(away, sv, -1))
    d = dict(step=st, t=t, p_bar=round(pbar, 3),
             uz_max=float(np.nanmax(U[:, 2])), uz_center=float(U[np.argmin(r + 1e3 * np.abs(z - P["t"])), 2]),
             lift_oring_max=float(np.nanmax(U[oring, 2])), lift_oring_min=float(np.nanmin(U[oring, 2])),
             vm_max=float(sv[k]), vm_max_at=[round(float(v), 1) for v in (r[k], z[k], dw[k])],
             vm_max_plate=float(sv[ka]), vm_plate_at=[round(float(v), 1) for v in (r[ka], z[ka])],
             s1_max=float(np.nanmax(pr[:, 2])), s3_min=float(np.nanmin(pr[:, 0])),
             vm_center_top=float(sv[np.argmin(r + 1e3 * np.abs(z - P["t"]))]),
             vm_center_bot=float(sv[np.argmin(r + 1e3 * np.abs(z))]),
             szz_washer_min=float(np.nanmin(S[wz, 2])), szz_washer_mean=float(np.nanmean(S[wz, 2])),
             washer_indent=float(np.nanmin(U[wz, 2]) - 0.0))
    d["SF_vm"] = SY / d["vm_max"]
    d["SF_plate"] = SY / d["vm_max_plate"]
    res.append(d)
    print(json.dumps(d))
json.dump(res, open(name + "_res.json", "w"), indent=1)

# ---------------- grafici (ultimo istante) ----------------
st, t = steps[-1]
U = nodal(field("DISP", t, st), D, 3)
S = nodal(field("STRESS", t, st), D, 6)
sv = vm(S)
A = math.radians(P["ang"])


def full_disc(xy, val, nrep=20):
    """replica il settore (0..9°) a disco intero: specchio + rotazioni di 18°"""
    th = np.arctan2(xy[:, 1], xy[:, 0]); rr = np.hypot(xy[:, 0], xy[:, 1])
    TH, RR, V = [], [], []
    for k in range(nrep):
        for sgn in (1, -1):
            TH.append(sgn * th + k * 2 * A); RR.append(rr); V.append(val)
    TH = np.concatenate(TH); RR = np.concatenate(RR); V = np.concatenate(V)
    return RR * np.cos(TH), RR * np.sin(TH), V


fig, axs = plt.subplots(1, 3, figsize=(17, 5.4))
for ax, (sel, val, lab, cmap) in zip(axs, [
        (np.abs(z) < 1e-4, U[:, 2], "Freccia $u_z$ [mm] (faccia inferiore)", "viridis"),
        (np.abs(z - P["t"]) < 1e-4, sv, "von Mises [MPa] faccia superiore (esterna)", "inferno"),
        (np.abs(z) < 1e-4, sv, "von Mises [MPa] faccia inferiore (lato pressione)", "inferno")]):
    xs, ys, vs = full_disc(xyz[sel, :2], val[sel])
    vmax = np.nanpercentile(vs, 99.9)
    tc = ax.tricontourf(mtri.Triangulation(xs, ys), vs, levels=np.linspace(np.nanmin(vs), vmax, 25), cmap=cmap, extend="max")
    plt.colorbar(tc, ax=ax, shrink=0.85)
    for rr_, ls in ((P["Rseal"], "--"), (P["Rb"], ":")):
        ph = np.linspace(0, 2 * np.pi, 300); ax.plot(rr_ * np.cos(ph), rr_ * np.sin(ph), "w", ls=ls, lw=0.8)
    ax.set_aspect("equal"); ax.set_title(lab, fontsize=10); ax.set_xticks([]); ax.set_yticks([])
fig.suptitle("DiscoPCU HDPE — p = %.1f bar, precarico %.1f kN/bullone (-- O-ring R%.1f, : cerchio bulloni R%.0f)"
             % (P["p"] * 10, P["F"] / 1e3, P["Rseal"], P["Rb"]))
fig.tight_layout(); fig.savefig(name + "_mappe.png", dpi=130)

# profili radiali
fig, ax = plt.subplots(1, 2, figsize=(13, 4.6))
for st_, t_ in steps:
    U_ = nodal(field("DISP", t_, st_), D, 3); S_ = nodal(field("STRESS", t_, st_), D, 6); sv_ = vm(S_)
    pb = 0 if st_ == 1 else P["p"] * t_ * 10
    for zz, ls in ((0.0, "-"), (P["t"], "--")):
        sel = (np.abs(z - zz) < 1e-4) & (np.abs(xyz[:, 1] - np.tan(A / 2) * xyz[:, 0]) < 2.5)  # raggio a 4.5°
        o = np.argsort(r[sel])
        if zz == 0.0:
            ax[0].plot(r[sel][o], U_[sel, 2][o], ls, label="%.1f bar" % pb)
        ax[1].plot(r[sel][o], sv_[sel][o], ls, label="%.1f bar %s" % (pb, "inf." if zz == 0 else "sup."))
ax[0].set_xlabel("raggio [mm]"); ax[0].set_ylabel("$u_z$ [mm]"); ax[0].set_title("Freccia lungo il raggio (a metà tra due bulloni)")
ax[1].set_xlabel("raggio [mm]"); ax[1].set_ylabel("von Mises [MPa]"); ax[1].set_title("von Mises lungo il raggio")
ax[1].axhline(SY, color="r", lw=0.8); ax[1].text(5, SY + 0.5, "snervamento %.0f MPa" % SY, color="r", fontsize=8)
for a in ax:
    a.axvline(P["Rseal"], color="k", lw=0.6, ls="--"); a.axvline(P["Rb"], color="k", lw=0.6, ls=":"); a.grid(alpha=0.3); a.legend(fontsize=7)
fig.tight_layout(); fig.savefig(name + "_profili.png", dpi=130)

# impronta rondella: sigma_zz sotto la rondella, zoom
dw = np.hypot(xyz[:, 0] - P["Rb"], xyz[:, 1])
fig, axs = plt.subplots(1, len(steps), figsize=(4.2 * len(steps), 4))
for ax, (st_, t_) in zip(np.atleast_1d(axs), steps):
    S_ = nodal(field("STRESS", t_, st_), D, 6)
    sel = (np.abs(z - P["t"]) < 1e-4) & (dw < P["rw_out"] + 6)
    x0 = xyz[sel, 0] - P["Rb"]; y0 = xyz[sel, 1]
    xs = np.concatenate([x0, x0]); ys = np.concatenate([y0, -y0]); vs = np.concatenate([-S_[sel, 2]] * 2)
    tc = ax.tricontourf(xs, ys, vs, levels=np.linspace(min(0, np.nanmin(vs)), np.nanpercentile(vs, 99.5), 21), cmap="magma", extend="both")
    plt.colorbar(tc, ax=ax, shrink=0.8)
    ph = np.linspace(0, 2 * np.pi, 100)
    for rr_ in (P["rh"], P["rw_out"]):
        ax.plot(rr_ * np.cos(ph), rr_ * np.sin(ph), "c", lw=0.7)
    ax.set_aspect("equal"); ax.set_title("pressione sotto rondella [MPa]\n%s" % ("solo precarico" if st_ == 1 else "%.1f bar" % (P["p"] * t_ * 10)), fontsize=9)
    ax.set_xlabel("radiale [mm] (→ esterno)")
fig.tight_layout(); fig.savefig(name + "_rondella.png", dpi=130)
print("ok")
