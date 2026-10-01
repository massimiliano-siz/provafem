"""Modello assialsimmetrico veloce del DiscoPCU (bulloni "spalmati" su anello rondelle).
x = raggio, y = quota. Elementi CAX8 (quad 8 nodi). Contatto disco/flangia.
"""
import sys, json, math
import numpy as np

P = dict(R=296.0, t=20.0, Rseal=208.5, rw1=270.0, rw2=290.0, nb=20, F=3000.0,
         p=0.3, E=1000.0, nu=0.40, h=1.0)
if len(sys.argv) > 1:
    P.update(json.loads(sys.argv[1]))
out = P.get("out", "axi")

def grid(r0, r1, z0, z1, nr, nz, nid0, eid0, X):
    """mesh strutturata quad8; restituisce elementi e mappa (i,j)->nodo su griglia 2x"""
    ids = {}
    nid = nid0
    for j in range(2 * nz + 1):
        for i in range(2 * nr + 1):
            if i % 2 and j % 2:
                continue
            nid += 1
            ids[i, j] = nid
            X[nid] = (r0 + (r1 - r0) * i / (2 * nr), z0 + (z1 - z0) * j / (2 * nz))
    E = []
    eid = eid0
    for j in range(nz):
        for i in range(nr):
            a, b = 2 * i, 2 * j
            eid += 1
            E.append((eid, [ids[a, b], ids[a + 2, b], ids[a + 2, b + 2], ids[a, b + 2],
                            ids[a + 1, b], ids[a + 2, b + 1], ids[a + 1, b + 2], ids[a, b + 1]]))
    return E, ids, nid, eid

X = {}
h = P["h"]
# disco: tre blocchi radiali per avere nodi esattamente a Rseal, rw1, rw2
segs = [(0, P["Rseal"]), (P["Rseal"], P["rw1"]), (P["rw1"], P["rw2"]), (P["rw2"], P["R"])]
nz = max(8, int(round(P["t"] / h)))
disc, nid, eid = [], 0, 0
blocks = []
# griglia semplice: r nodi da concatenazione
rnodes = [0.0]
for a, b in segs:
    n = max(2, int(round((b - a) / h)))
    rnodes += list(np.linspace(a, b, 2 * n + 1))[1:]
rnodes = np.array(rnodes)
znodes = np.linspace(0, P["t"], 2 * nz + 1)
ids = {}
for j, zz in enumerate(znodes):
    for i, r_ in enumerate(rnodes):
        if i % 2 and j % 2:
            continue
        nid += 1; ids[i, j] = nid; X[nid] = (r_, zz)
for j in range(nz):
    for i in range((len(rnodes) - 1) // 2):
        a, b = 2 * i, 2 * j
        eid += 1
        disc.append((eid, [ids[a, b], ids[a + 2, b], ids[a + 2, b + 2], ids[a, b + 2],
                           ids[a + 1, b], ids[a + 2, b + 1], ids[a + 1, b + 2], ids[a, b + 1]]))
NR = len(rnodes) - 1
# flangia (Al) sotto, da Rseal a R+4, spessore 10
fl, fids, nid, eid = grid(P["Rseal"], P["R"] + 4, -10.0, 0.0, int((P["R"] + 4 - P["Rseal"]) / 3), 3, nid, eid, X)
FNR = 2 * int((P["R"] + 4 - P["Rseal"]) / 3)

# superfici: CAX8 facce S1=(1-2) S2=(2-3) S3=(3-4) S4=(4-1)
press, dbot, wtop, ftop = [], [], [], []
for k, (e, c) in enumerate(disc):
    i, j = k % (NR // 2), k // (NR // 2)
    r0, r1 = X[c[0]][0], X[c[1]][0]
    rm = 0.5 * (r0 + r1)
    if j == 0:
        (press if rm < P["Rseal"] else dbot).append((e, 1))
    if j == nz - 1 and P["rw1"] <= rm <= P["rw2"]:
        wtop.append((e, 3))
for k, (e, c) in enumerate(fl):
    if k >= len(fl) - FNR // 2:
        ftop.append((e, 3))
wnodes = sorted({n for e, c in disc for n in c if abs(X[n][1] - P["t"]) < 1e-9 and P["rw1"] - 1e-9 <= X[n][0] <= P["rw2"] + 1e-9})
axis = sorted({n for e, c in disc for n in c if abs(X[n][0]) < 1e-9})
flbot = sorted({n for e, c in fl for n in c if abs(X[n][1] + 10) < 1e-9})
# nodo per vincolo radiale (gambo vite), a meta' spessore su R=rw1+... (simula il foro)
radn = min((n for e, c in disc for n in c), key=lambda n: abs(X[n][0] - 0.5 * (P["rw1"] + P["rw2"])) + abs(X[n][1] - P["t"] / 2))

Aring = math.pi * (P["rw2"] ** 2 - P["rw1"] ** 2)
q = P["nb"] * P["F"] / Aring

def wset(f, name, ids_):
    f.write("*NSET,NSET=%s\n" % name)
    for i in range(0, len(ids_), 16):
        f.write(",".join(map(str, ids_[i:i + 16])) + ",\n")

with open(out + ".inp", "w") as f:
    f.write("*HEADING\nDiscoPCU assialsimmetrico\n*NODE\n")
    for n, (x, y) in X.items():
        f.write("%d,%.6f,%.6f,0\n" % (n, x, y))
    for nm, E_ in (("DISC", disc), ("FLANGE", fl)):
        f.write("*ELEMENT,TYPE=CAX8,ELSET=%s\n" % nm)
        for e, c in E_:
            f.write("%d,%s\n" % (e, ",".join(map(str, c))))
    wset(f, "WN", wnodes); wset(f, "AXIS", axis); wset(f, "FLBOT", flbot)
    for nm, L in (("SPRESS", press), ("SDBOT", dbot), ("SWTOP", wtop), ("SFTOP", ftop)):
        f.write("*SURFACE,NAME=%s,TYPE=ELEMENT\n" % nm)
        for e, k in L:
            f.write("%d,S%d\n" % (e, k))
    f.write("""*MATERIAL,NAME=HDPE
*ELASTIC
{E},{nu}
*MATERIAL,NAME=ALU
*ELASTIC
70000,0.33
*SOLID SECTION,ELSET=DISC,MATERIAL=HDPE
*SOLID SECTION,ELSET=FLANGE,MATERIAL=ALU
*SURFACE INTERACTION,NAME=SI
*SURFACE BEHAVIOR,PRESSURE-OVERCLOSURE=LINEAR
2.e4,0.01
*CONTACT PAIR,INTERACTION=SI,TYPE=SURFACE TO SURFACE
SDBOT,SFTOP
*BOUNDARY
AXIS,1,1
FLBOT,1,2
*TIME POINTS,NAME=TP
0.1666667,0.3333333,0.5,0.6666667,0.8333333,1.0
*STEP,NLGEOM,INC=500
*STATIC
0.25,1.0,1.e-6,0.5
*DLOAD
SWTOP,P3,{q}
*NODE FILE
U
*EL FILE
S,E
*CONTACT FILE
CSTR,CDIS
*END STEP
*STEP,NLGEOM,INC=500
*STATIC
0.05,1.0,1.e-6,0.1
*BOUNDARY,FIXED
WN,2,2
*DLOAD,OP=NEW
SPRESS,P1,{p}
*NODE PRINT,NSET=WN,TOTALS=ONLY
RF
*NODE FILE,TIME POINTS=TP
U
*EL FILE,TIME POINTS=TP
S,E
*CONTACT FILE,TIME POINTS=TP
CSTR,CDIS
*END STEP
""".format(E=P["E"], nu=P["nu"], q=q, p=P["p"], RADN=radn))
json.dump(dict(P=P, q_washer_ring=q, nodes=len(X), elems=len(disc) + len(fl)), open(out + "_info.json", "w"), indent=1)
print("nodi", len(X), "elementi", len(disc) + len(fl), "q anello", q)
