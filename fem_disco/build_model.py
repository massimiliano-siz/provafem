"""Modello FEM del DiscoPCU (HDPE) — settore 9° con simmetria ciclica-speculare.

Geometria (ricavata da Assembly_6.step, origine traslata al centro del disco):
  disco R=296, spessore 20, 20 fori Ø10.5 su R=280
  O-ring: cava sul distributore R 203.5–208.5 -> pressione fino a R=208.5
  flangia distributore (appoggio) da R=208.5 verso l'esterno, piano z=0
Parti: disco HDPE, rondella acciaio (contatto), blocco flangia Al (contatto).
"""
import math, sys, json
import gmsh
import numpy as np

P = dict(R=296.0, t=20.0, Rb=280.0, rh=5.25, Rseal=208.5,
         rw_out=10.0, tw=2.0,          # rondella ISO 7089 M10: 10.5/20 x 2
         ang=9.0,                      # semi-passo angolare (20 bulloni)
         F=3000.0,                     # precarico per bullone [N]
         p=0.3,                        # pressione [MPa]
         E=1000.0, nu=0.40,            # HDPE
         h_glob=4.5, h_fine=1.2, h_seal=2.0)
if len(sys.argv) > 1:
    P.update(json.loads(sys.argv[1]))
out = P.get("out", "disco")
A = math.radians(P["ang"])

gmsh.initialize()
gmsh.option.setNumber("General.Verbosity", 1)
occ = gmsh.model.occ

# --- disco: faccia 2D partizionata, poi estrusa --------------------------------
base = occ.addCylinder(0, 0, 0, 0, 0, P["t"], P["R"], angle=A)
hole = occ.addCylinder(P["Rb"], 0, -1, 0, 0, P["t"] + 2, P["rh"])
disc, _ = occ.cut([(3, base)], [(3, hole)])
# partizioni: cilindro R=Rseal (pressione/contatto in basso), cilindro attorno al foro (rondella)
cs = occ.addCylinder(0, 0, -1, 0, 0, P["t"] + 2, P["Rseal"])
cw = occ.addCylinder(P["Rb"], 0, -1, 0, 0, P["t"] + 2, P["rw_out"])
frag, fmap = occ.fragment(disc, [(3, cs), (3, cw)])
occ.synchronize()
# tieni solo i volumi dentro il settore del disco
keep = []
for d, tg in frag:
    xmin, ymin, zmin, xmax, ymax, zmax = gmsh.model.getBoundingBox(3, tg)
    if zmin > -0.5 and zmax < P["t"] + 0.5:
        keep.append(tg)
rm = [(3, tg) for d, tg in frag if tg not in keep]
occ.remove(rm, recursive=True)
occ.synchronize()
disc_vols = [tg for d, tg in gmsh.model.getEntities(3)]

# --- rondella (mezza) ----------------------------------------------------------
w1 = occ.addCylinder(P["Rb"], 0, P["t"], 0, 0, P["tw"], P["rw_out"])
w2 = occ.addCylinder(P["Rb"], 0, P["t"] - 1, 0, 0, P["tw"] + 2, P["rh"])
wa, _ = occ.cut([(3, w1)], [(3, w2)])
box = occ.addBox(P["Rb"] - 20, -20, P["t"] - 1, 40, 20, P["tw"] + 2)
wh, _ = occ.cut(wa, [(3, box)])
# --- blocco flangia ------------------------------------------------------------
fl = occ.addCylinder(0, 0, -10, 0, 0, 10, P["R"] + 4, angle=A)
fi = occ.addCylinder(0, 0, -11, 0, 0, 12, P["Rseal"])
flv, _ = occ.cut([(3, fl)], [(3, fi)])
occ.synchronize()
washer_vol = wh[0][1]
fl_vol = flv[0][1]

# --- mesh size -----------------------------------------------------------------
f1 = gmsh.model.mesh.field.add("MathEval")
expr = ("Min({g}, {f}+0.12*Max(0,Sqrt((x-{Rb})^2+y^2)-{rw}),"
        " {s}+0.15*Abs(Sqrt(x^2+y^2)-{Rs}))").format(
    g=P["h_glob"], f=P["h_fine"], Rb=P["Rb"], rw=P["rw_out"], s=P["h_seal"], Rs=P["Rseal"])
gmsh.model.mesh.field.setString(f1, "F", expr)
gmsh.model.mesh.field.setAsBackgroundMesh(f1)
gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 0)
gmsh.option.setNumber("Mesh.MeshSizeFromPoints", 0)
gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 0)
# master (rondella e flangia) piu' grossolani del slave
for tg, h in ((washer_vol, 2.0), (fl_vol, 5.0)):
    gmsh.model.mesh.setSize(gmsh.model.getBoundary([(3, tg)], recursive=True, combined=False), h)
fr = gmsh.model.mesh.field.add("Restrict")
gmsh.model.mesh.field.setNumbers(fr, "VolumesList", disc_vols)
gmsh.model.mesh.field.setNumber(fr, "InField", f1)
fc = gmsh.model.mesh.field.add("Constant")
gmsh.model.mesh.field.setNumbers(fc, "VolumesList", [washer_vol])
gmsh.model.mesh.field.setNumber(fc, "VIn", 2.0)
fc2 = gmsh.model.mesh.field.add("Constant")
gmsh.model.mesh.field.setNumbers(fc2, "VolumesList", [fl_vol])
gmsh.model.mesh.field.setNumber(fc2, "VIn", 5.0)
fmin = gmsh.model.mesh.field.add("Min")
gmsh.model.mesh.field.setNumbers(fmin, "FieldsList", [fr, fc, fc2])
gmsh.model.mesh.field.setAsBackgroundMesh(fmin)
gmsh.option.setNumber("Mesh.ElementOrder", 2)
gmsh.option.setNumber("Mesh.SecondOrderLinear", 0)
gmsh.option.setNumber("Mesh.HighOrderOptimize", 1)
gmsh.option.setNumber("Mesh.Algorithm3D", 10)
gmsh.model.mesh.generate(3)

# --- estrazione --------------------------------------------------------------
ntags, xyz, _ = gmsh.model.mesh.getNodes()
X = dict(zip(ntags.astype(int), xyz.reshape(-1, 3)))

def tets(vol):
    et, el, nd = gmsh.model.mesh.getElements(3, vol)
    i = list(et).index(11)  # tet10
    return el[i].astype(int), nd[i].astype(int).reshape(-1, 10)

parts = {"DISC": [], "WASHER": [], "FLANGE": []}
for v in disc_vols:
    parts["DISC"].append(tets(v))
parts["WASHER"].append(tets(washer_vol))
parts["FLANGE"].append(tets(fl_vol))

# gmsh tet10 -> ccx C3D10: ordine nodi gmsh 0-3 vertici, 4:(0,1) 5:(1,2) 6:(2,0) 7:(3,0) 8:(3,2)? -> verifichiamo
# gmsh: 4=(0,1) 5=(1,2) 6=(0,2) 7=(0,3) 8=(2,3) 9=(1,3); ccx/abaqus: 5=(1,2) 6=(2,3) 7=(3,1) 8=(1,4) 9=(2,4) 10=(3,4)
perm = [0, 1, 2, 3, 4, 5, 6, 7, 9, 8]

elems = {}
for name, lst in parts.items():
    E_ = []
    for etags, conn in lst:
        for e, c in zip(etags, conn):
            E_.append((e, c[perm]))
    elems[name] = E_

used = set()
for lst in elems.values():
    for e, c in lst:
        used.update(c.tolist())

# facce: ccx C3D10 S1=(1,2,3) S2=(1,4,2) S3=(2,4,3) S4=(3,4,1)
FACES = [(0, 1, 2), (0, 3, 1), (1, 3, 2), (2, 3, 0)]

def face_list(name, pred):
    """facce di bordo degli elementi della parte che soddisfano pred(centroide, normale)."""
    cnt = {}
    for e, c in elems[name]:
        for k, f in enumerate(FACES):
            key = tuple(sorted(c[list(f)]))
            cnt.setdefault(key, []).append((e, k, c))
    res = []
    for key, v in cnt.items():
        if len(v) != 1:
            continue
        e, k, c = v[0]
        pts = np.array([X[n] for n in c[list(FACES[k])]])
        cen = pts.mean(0)
        nrm = np.cross(pts[1] - pts[0], pts[2] - pts[0])
        nrm /= np.linalg.norm(nrm)
        if pred(cen, nrm):
            res.append((e, k + 1, c[list(FACES[k])]))
    return res

r = lambda c: math.hypot(c[0], c[1])
tol = 1e-4
disc_bot_in = face_list("DISC", lambda c, n: abs(c[2]) < tol and r(c) < P["Rseal"])
disc_bot_out = face_list("DISC", lambda c, n: abs(c[2]) < tol and r(c) > P["Rseal"])
disc_top_w = face_list("DISC", lambda c, n: abs(c[2] - P["t"]) < tol and math.hypot(c[0] - P["Rb"], c[1]) < P["rw_out"])
wash_bot = face_list("WASHER", lambda c, n: abs(c[2] - P["t"]) < tol)
fl_top = face_list("FLANGE", lambda c, n: abs(c[2]) < tol)

def nodes_where(name, pred):
    s = set()
    for e, c in elems[name]:
        for nn in c:
            if pred(X[nn]):
                s.add(int(nn))
    return sorted(s)

on_p0 = lambda x: abs(x[1]) < 1e-5
on_p1 = lambda x: abs(-math.sin(A) * x[0] + math.cos(A) * x[1]) < 1e-5
axis = lambda x: math.hypot(x[0], x[1]) < 1e-6
sym_disc = nodes_where("DISC", lambda x: (on_p0(x) or on_p1(x)) and not axis(x))
axis_n = nodes_where("DISC", axis)
w_top = nodes_where("WASHER", lambda x: abs(x[2] - P["t"] - P["tw"]) < 1e-5)
sym_w = [n for n in nodes_where("WASHER", on_p0) if n not in set(w_top)]
fl_bot = nodes_where("FLANGE", lambda x: abs(x[2] + 10) < 1e-5)
sym_fl = [n for n in nodes_where("FLANGE", lambda x: on_p0(x) or on_p1(x)) if n not in set(fl_bot)]

# nodo sul foro, lato interno, a meta' spessore, sul piano di simmetria 0
cand = [n for n in sym_disc if abs(math.hypot(X[n][0]-P["Rb"], X[n][1]) - P["rh"]) < 1e-4 and X[n][0] < P["Rb"]]
radn = min(cand, key=lambda n: abs(X[n][2] - P["t"]/2))
nmax = max(used)
REF, ROT = nmax + 1, nmax + 2

def wset(f, name, ids, per=16):
    f.write("*NSET,NSET=%s\n" % name)
    for i in range(0, len(ids), per):
        f.write(",".join(str(v) for v in ids[i:i + per]) + ",\n")

def wsurf(f, name, lst):
    f.write("*SURFACE,NAME=%s,TYPE=ELEMENT\n" % name)
    for e, k, _ in lst:
        f.write("%d,S%d\n" % (e, k))

with open(out + ".inp", "w") as f:
    f.write("*HEADING\nDiscoPCU HDPE settore 9 gradi\n*NODE\n")
    for n in sorted(used):
        f.write("%d,%.6f,%.6f,%.6f\n" % (n, *X[n]))
    f.write("%d,%.6f,0,%.6f\n%d,%.6f,0,%.6f\n" % (REF, P["Rb"], P["t"] + P["tw"], ROT, P["Rb"], P["t"] + P["tw"]))
    for name, lst in elems.items():
        f.write("*ELEMENT,TYPE=C3D10,ELSET=%s\n" % name)
        for e, c in lst:
            f.write("%d,%s\n" % (e, ",".join(str(v) for v in c)))
    wset(f, "SYMD", sym_disc); wset(f, "AXIS", axis_n); wset(f, "WTOP", w_top)
    wset(f, "SYMW", sym_w); wset(f, "FLBOT", fl_bot); wset(f, "SYMF", sym_fl)
    wset(f, "SYMALL", sorted(set(sym_disc) | set(sym_w) | set(sym_fl)))
    # nodi lungo la linea di tenuta (fondo disco) per output
    f.write("*TRANSFORM,NSET=SYMALL,TYPE=C\n0,0,0,0,0,1\n")
    wsurf(f, "SPRESS", disc_bot_in); wsurf(f, "SDBOT", disc_bot_out)
    wsurf(f, "SDTOP", disc_top_w); wsurf(f, "SWBOT", wash_bot); wsurf(f, "SFTOP", fl_top)
    f.write("""*MATERIAL,NAME=HDPE
*ELASTIC
{E},{nu}
*MATERIAL,NAME=STEEL
*ELASTIC
210000,0.3
*MATERIAL,NAME=ALU
*ELASTIC
70000,0.33
*SOLID SECTION,ELSET=DISC,MATERIAL=HDPE
*SOLID SECTION,ELSET=WASHER,MATERIAL=STEEL
*SOLID SECTION,ELSET=FLANGE,MATERIAL=ALU
*RIGID BODY,NSET=WTOP,REF NODE={REF},ROT NODE={ROT}
*SURFACE INTERACTION,NAME=SI
*SURFACE BEHAVIOR,PRESSURE-OVERCLOSURE=LINEAR
2.e4,0.01
*SURFACE INTERACTION,NAME=SIG
*SURFACE BEHAVIOR,PRESSURE-OVERCLOSURE=LINEAR
{KG},0.001
*CONTACT PAIR,INTERACTION=SIG,TYPE=SURFACE TO SURFACE
SDBOT,SFTOP
*CONTACT PAIR,INTERACTION=SI,TYPE=SURFACE TO SURFACE
SDTOP,SWBOT
*BOUNDARY
SYMALL,2,2
{RADN},1,1
AXIS,1,2
FLBOT,1,3
{REF},1,2
{ROT},1,3
*TIME POINTS,NAME=TP
0.3333333,0.6666667,1.0
*STEP,NLGEOM,INC=500
*STATIC
0.5,1.0,1.e-6,1.0
*CONTROLS,PARAMETERS=FIELD
0.02,0.05
*CONTROLS,PARAMETERS=TIME INCREMENTATION
8,10,9,200,10,4,,10
*CLOAD
{REF},3,{Fh}
*NODE PRINT,NSET=WTOP,TOTALS=ONLY
RF
*NODE FILE
U
*EL FILE
S,E
*CONTACT FILE
CSTR,CDIS
*END STEP
*STEP,NLGEOM,INC=500
*STATIC
0.1666667,1.0,1.e-6,0.3333333
*BOUNDARY,FIXED
{REF},3,3
*CLOAD,OP=NEW
{REF},3,0.
*DLOAD
SPRESS,P,{p}
*NODE FILE,TIME POINTS=TP
U
*EL FILE,TIME POINTS=TP
S,E
*CONTACT FILE,TIME POINTS=TP
CSTR,CDIS
*END STEP
""".format(E=P["E"], nu=P["nu"], REF=REF, ROT=ROT, Fh=-P["F"] / 2, p=P["p"], RADN=radn, KG=P.get("Kg", 2.e4)))

json.dump({"P": P, "nodes": len(used), "elems": {k: len(v) for k, v in elems.items()},
           "faces": dict(press=len(disc_bot_in), dbot=len(disc_bot_out), dtop=len(disc_top_w),
                         wbot=len(wash_bot), ftop=len(fl_top)), "REF": REF},
          open(out + "_info.json", "w"), indent=1)
print(open(out + "_info.json").read())
gmsh.write(out + "_mesh.msh")
gmsh.finalize()
