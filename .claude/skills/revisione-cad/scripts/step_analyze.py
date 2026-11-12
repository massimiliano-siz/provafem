#!/usr/bin/env python3
"""Analisi geometrica di file STEP (parti e assiemi) con OpenCASCADE.

Uso: step_analyze.py <file.step> [...] --out <dir> [--density g/cm3]

Per ogni file produce <out>/<nome>/step.json e summary.md con:
  - albero dell'assieme e istanze (posizione globale)
  - per ogni parte: ingombri, volume, massa (se densità nota), feature riconosciute
    (cilindri interni/esterni raggruppati, profilo assiale per pezzi torniti, fori fuori asse
    con PCD, fori radiali, raccordi, coni/smussi, spessore minimo di parete radiale)
  - per gli assiemi: interferenze (volume comune), contatti, giochi minimi e accoppiamenti
    cilindrici coassiali tra parti diverse (foro/albero con gioco diametrale)

Unità: mm. Le filettature in genere NON sono modellate nello STEP: vanno lette dal disegno.
"""
import argparse, json, math, os, re, sys
from collections import defaultdict

from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.TDocStd import TDocStd_Document
from OCP.TCollection import TCollection_ExtendedString
from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ShapeTool
from OCP.TDF import TDF_LabelSequence, TDF_Label
from OCP.TDataStd import TDataStd_Name
from OCP.TopLoc import TopLoc_Location
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE, TopAbs_SOLID, TopAbs_REVERSED
from OCP.TopoDS import TopoDS
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Plane, GeomAbs_Cylinder, GeomAbs_Cone, GeomAbs_Torus, GeomAbs_Sphere
from OCP.BRepTools import BRepTools
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.gp import gp_Pnt, gp_Vec
from OCP.BRepLProp import BRepLProp_SLProps

TOL = 1e-3
MIN_INTERFERENCE_MM3 = 0.05  # sotto: errore numerico/tangenza, trattato come contatto

# ISO 261: passi grosso e fini per diametro nominale (mm)
ISO_PITCHES = {3: [0.5, 0.35], 4: [0.7, 0.5], 5: [0.8, 0.5], 6: [1, 0.75], 8: [1.25, 1, 0.75], 10: [1.5, 1.25, 1, 0.75],
               12: [1.75, 1.5, 1.25, 1], 14: [2, 1.5, 1.25, 1], 16: [2, 1.5, 1], 18: [2.5, 2, 1.5, 1], 20: [2.5, 2, 1.5, 1],
               22: [2.5, 2, 1.5, 1], 24: [3, 2, 1.5, 1], 27: [3, 2, 1.5, 1], 30: [3.5, 3, 2, 1.5, 1], 33: [3.5, 3, 2, 1.5],
               36: [4, 3, 2, 1.5], 42: [4.5, 4, 3, 2, 1.5], 48: [5, 4, 3, 2, 1.5]}


def thread_guess(shaft_dia, hole_dia):
    """Se albero = Ø nominale e foro = Ø di preparazione (≈ D − P), è una filettatura non modellata."""
    D = round(shaft_dia, 2)
    if abs(D - round(D)) > 0.01 or int(round(D)) not in ISO_PITCHES:
        return None
    for P in ISO_PITCHES[int(round(D))]:
        if abs((D - P) - hole_dia) < 0.06:
            return f"M{int(round(D))}x{str(P).replace('.', ',')}"
    return None


def label_name(lab):
    n = TDataStd_Name()
    if lab.FindAttribute(TDataStd_Name.GetID_s(), n):
        return n.Get().ToExtString()
    return ""


def read_step(path):
    doc = TDocStd_Document(TCollection_ExtendedString("doc"))
    r = STEPCAFControl_Reader()
    r.SetNameMode(True); r.SetColorMode(True)
    if r.ReadFile(path) != 1:
        raise RuntimeError(f"Impossibile leggere {path}")
    r.Transfer(doc)
    st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    roots = TDF_LabelSequence(); st.GetFreeShapes(roots)
    instances, parts, tree = [], {}, []

    def walk(lab, loc, path, depth):
        name = label_name(lab)
        if XCAFDoc_ShapeTool.IsAssembly_s(lab):
            tree.append({"depth": depth, "name": name, "type": "assembly"})
            comps = TDF_LabelSequence(); XCAFDoc_ShapeTool.GetComponents_s(lab, comps)
            for i in range(1, comps.Length() + 1):
                c = comps.Value(i)
                ref = TDF_Label(); XCAFDoc_ShapeTool.GetReferredShape_s(c, ref)
                cl = XCAFDoc_ShapeTool.GetLocation_s(c)
                walk(ref, loc.Multiplied(cl), path + [label_name(c) or label_name(ref)], depth + 1)
        else:
            shape = XCAFDoc_ShapeTool.GetShape_s(lab)
            key = lab.Tag()
            pid = f"{name or 'part'}#{key}"
            if pid not in parts:
                parts[pid] = {"name": name or "part", "shape": shape}
            tree.append({"depth": depth, "name": name, "type": "part", "part_id": pid})
            instances.append({"part_id": pid, "name": name, "path": " / ".join(path),
                              "shape": shape.Located(loc)})

    for i in range(1, roots.Length() + 1):
        walk(roots.Value(i), TopLoc_Location(), [label_name(roots.Value(i))], 0)
    return tree, parts, instances


def props(shape):
    g = GProp_GProps(); BRepGProp.VolumeProperties_s(shape, g)
    a = GProp_GProps(); BRepGProp.SurfaceProperties_s(shape, a)
    b = Bnd_Box(); BRepBndLib.AddOptimal_s(shape, b, False, False)
    x0, y0, z0, x1, y1, z1 = b.Get()
    c = g.CentreOfMass()
    return {"volume_mm3": round(g.Mass(), 1), "area_mm2": round(a.Mass(), 1),
            "bbox_mm": [round(x0, 3), round(y0, 3), round(z0, 3), round(x1, 3), round(y1, 3), round(z1, 3)],
            "size_mm": [round(x1 - x0, 3), round(y1 - y0, 3), round(z1 - z0, 3)],
            "com_mm": [round(c.X(), 3), round(c.Y(), 3), round(c.Z(), 3)]}


def vec(d):
    return (d.X(), d.Y(), d.Z())


def canon_dir(d):
    x, y, z = d
    n = math.sqrt(x * x + y * y + z * z) or 1
    x, y, z = x / n, y / n, z / n
    # verso canonico
    for c in (x, y, z):
        if abs(c) > 1e-6:
            if c < 0:
                x, y, z = -x, -y, -z
            break
    return (round(x, 4) + 0.0, round(y, 4) + 0.0, round(z, 4) + 0.0)


def dot(a, b):
    return sum(i * j for i, j in zip(a, b))


def sub(a, b):
    return tuple(i - j for i, j in zip(a, b))


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def norm(a):
    return math.sqrt(dot(a, a))


def line_foot(p, o, d):
    """Punto dell'asse (o,d) più vicino all'origine del riferimento: identifica la retta."""
    t = dot(sub(p, o), d)
    return tuple(o[i] + t * d[i] for i in range(3))


def axis_key(o, d):
    # rappresentazione univoca della retta: punto più vicino all'origine
    t = -dot(o, d)
    q = tuple(o[i] + t * d[i] for i in range(3))
    return (canon_dir(d), tuple(round(v, 2) + 0.0 for v in q))


def face_normal_mid(face):
    s = BRepAdaptor_Surface(face, True)
    u0, u1, v0, v1 = BRepTools.UVBounds_s(face)
    u, v = (u0 + u1) / 2, (v0 + v1) / 2
    pr = BRepLProp_SLProps(s, u, v, 1, 1e-6)
    if not pr.IsNormalDefined():
        return None, None
    n = pr.Normal()
    if face.Orientation() == TopAbs_REVERSED:
        n.Reverse()
    p = pr.Value()
    return (p.X(), p.Y(), p.Z()), (n.X(), n.Y(), n.Z())


def analyze_faces(shape):
    cyl, planes, tori, cones, other = [], [], [], [], defaultdict(int)
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        f = TopoDS.Face_s(exp.Current()); exp.Next()
        s = BRepAdaptor_Surface(f, True)
        t = s.GetType()
        g = GProp_GProps(); BRepGProp.SurfaceProperties_s(f, g); area = g.Mass()
        u0, u1, v0, v1 = BRepTools.UVBounds_s(f)
        if t == GeomAbs_Cylinder:
            c = s.Cylinder(); ax = c.Axis(); o = vec(ax.Location()); d = vec(ax.Direction())
            p, n = face_normal_mid(f)
            radial = sub(p, line_foot(p, o, d)) if p else None
            internal = (dot(radial, n) < 0) if (p and n and norm(radial) > 1e-9) else None
            # estremi assiali (punti 3D reali, proiettati dopo sull'asse canonico)
            p0, p1 = vec(s.Value(u0, v0)), vec(s.Value(u0, v1))
            cyl.append({"r": c.Radius(), "o": o, "d": d, "internal": internal, "area": area,
                        "span_deg": round(math.degrees(u1 - u0), 1), "p0": p0, "p1": p1})
        elif t == GeomAbs_Plane:
            pl = s.Plane(); p, n = face_normal_mid(f)
            planes.append({"o": vec(pl.Location()), "n": n or vec(pl.Axis().Direction()), "area": area, "p": p})
        elif t == GeomAbs_Torus:
            tr = s.Torus(); ax = tr.Axis()
            tori.append({"R": tr.MajorRadius(), "r": tr.MinorRadius(), "o": vec(ax.Location()), "d": vec(ax.Direction()), "area": area})
        elif t == GeomAbs_Cone:
            co = s.Cone(); ax = co.Axis()
            cones.append({"ref_r": co.RefRadius(), "half_angle_deg": math.degrees(co.SemiAngle()), "o": vec(ax.Location()),
                          "d": vec(ax.Direction()), "area": area, "apex": vec(co.Apex())})
        else:
            other[str(t).split(".")[-1]] += 1
    return cyl, planes, tori, cones, dict(other)


def part_features(shape):
    cyl, planes, tori, cones, other = analyze_faces(shape)
    # 1) asse principale: retta con più area di superfici di rivoluzione
    axes = defaultdict(float)
    for c in cyl:
        axes[axis_key(c["o"], c["d"])] += c["area"]
    for c in cones + tori:
        axes[axis_key(c["o"], c["d"])] += c["area"]
    rev_area = sum(c["area"] for c in cyl + cones + tori)
    main = max(axes.items(), key=lambda kv: kv[1]) if axes else None
    main_axis = None
    if main:
        (d, q), a = main
        main_axis = {"dir": list(d), "point": list(q), "share_of_revolved_area": round(a / rev_area, 3) if rev_area else 0}
    md = main[0][0] if main else None
    mq = main[0][1] if main else None

    def on_main(o, d):
        return main and axis_key(o, d) == main[0]

    def axial(o, d):
        # posizione lungo l'asse principale (origine nel punto canonico)
        return dot(sub(o, mq), md)

    # 2) cilindri raggruppati per (retta, raggio, interno/esterno)
    # ogni faccia → intervallo assiale; facce dello stesso gruppo e contigue → un unico tratto
    raw = defaultdict(list)
    for c in cyl:
        ak = axis_key(c["o"], c["d"])
        d, q = ak
        t0, t1 = sorted(dot(sub(pnt, q), d) for pnt in (c["p0"], c["p1"]))
        raw[(ak, round(c["r"], 4), c["internal"])].append((t0, t1, c["span_deg"], c["area"]))
    groups = {}
    for k, ivs in raw.items():
        ivs.sort()
        merged = []
        for t0, t1, sp, ar in ivs:
            if merged and t0 <= merged[-1]["a1"] + 1e-4 and (abs(t0 - merged[-1]["a0"]) > 1e-4 or True):
                m = merged[-1]
                if t0 <= m["a1"] + 1e-4:
                    m["a1"] = max(m["a1"], t1); m["span"] = max(m["span"], sp) if abs(t0 - m["a0"]) > 1e-4 else m["span"] + sp
                    m["faces"] += 1; m["area"] += ar
                    continue
            merged.append({"a0": t0, "a1": t1, "span": sp, "faces": 1, "area": ar})
        for n, m in enumerate(merged):
            groups[k + (n,)] = m
    profile, holes_off, holes_radial, other_cyl = [], [], [], []
    for (ak, r, internal, _n), g in groups.items():
        d, q = ak
        a0, a1 = g["a0"], g["a1"]
        entry = {"dia": round(2 * r, 3), "internal": internal, "len": round(a1 - a0, 3), "full_turn": g["span"] >= 359,
                 "faces": g["faces"]}
        if main and ak == main[0]:
            entry.update({"from": round(a0, 3), "to": round(a1, 3)})
            profile.append(entry)
        else:
            entry.update({"axis_dir": list(d), "axis_point": [round(v, 3) for v in q],
                          "start_mm": [round(q[i] + a0 * d[i], 3) for i in range(3)],
                          "end_mm": [round(q[i] + a1 * d[i], 3) for i in range(3)]})
            if md is not None:
                par = abs(abs(dot(d, md)) - 1) < 1e-3
                perp = abs(dot(d, md)) < 1e-3
                entry["parallel_to_main"] = par; entry["perpendicular_to_main"] = perp
                if par:
                    foot = line_foot(q, mq, md)
                    entry["radial_offset"] = round(norm(sub(q, foot)), 3)
                    holes_off.append(entry)
                elif perp:
                    holes_radial.append(entry)
                else:
                    other_cyl.append(entry)
            else:
                other_cyl.append(entry)
    profile.sort(key=lambda e: (e["from"], e["dia"]))
    # 3) pattern di fori paralleli all'asse: stesso diametro, stessa distanza radiale
    patterns = defaultdict(list)
    for h in holes_off:
        patterns[(h["dia"], h["internal"], round(h["radial_offset"], 2))].append(h)
    pats = []
    for (dia, internal, off), hs in patterns.items():
        angs = []
        if md is not None:
            # angolo attorno all'asse principale
            ref = cross(md, (1, 0, 0)) if abs(md[0]) < 0.9 else cross(md, (0, 1, 0))
            ref = tuple(v / norm(ref) for v in ref); ref2 = cross(md, ref)
            for h in hs:
                v = sub(tuple(h["axis_point"]), line_foot(tuple(h["axis_point"]), mq, md))
                angs.append(round(math.degrees(math.atan2(dot(v, ref2), dot(v, ref))) % 360, 2))
        pats.append({"count": len(hs), "dia": dia, "internal": internal, "pcd": round(2 * off, 3),
                     "angles_deg": sorted(angs), "len": [h["len"] for h in hs]})
    # 4) raccordi e smussi
    fillets = sorted({round(t["r"], 3) for t in tori})
    cone_list = []
    for c in cones:
        cone_list.append({"half_angle_deg": round(c["half_angle_deg"], 2), "ref_dia": round(2 * c["ref_r"], 3),
                          "on_main_axis": bool(on_main(c["o"], c["d"]))})
    # 5) spessore minimo di parete radiale (solo per pezzi di rivoluzione)
    walls = []
    if profile:
        ext = [p for p in profile if p["internal"] is False]
        inn = [p for p in profile if p["internal"] is True]
        for e in ext:
            for i in inn:
                lo, hi = max(e["from"], i["from"]), min(e["to"], i["to"])
                if hi - lo > 0.01 and e["dia"] > i["dia"]:
                    walls.append({"wall": round((e["dia"] - i["dia"]) / 2, 3), "ext_dia": e["dia"], "int_dia": i["dia"],
                                  "from": round(lo, 3), "to": round(hi, 3)})
        walls.sort(key=lambda w: w["wall"])
    # 6) facce piane perpendicolari all'asse: quote assiali
    steps = []
    if md is not None:
        for p in planes:
            if p["n"] and abs(abs(dot(p["n"], md)) - 1) < 1e-3:
                steps.append(round(dot(sub(p["o"], mq), md), 3))
    steps = sorted(set(steps))
    return {
        "main_axis": main_axis,
        "is_revolved": bool(main_axis and main_axis["share_of_revolved_area"] > 0.5),
        "axial_profile": profile,
        "axial_planes": steps,
        "hole_patterns_parallel": pats,
        "radial_holes": holes_radial,
        "other_cylinders": other_cyl,
        "fillet_radii": fillets,
        "cones": cone_list,
        "min_radial_walls": walls[:8],
        "face_counts": {"cylinder": len(cyl), "plane": len(planes), "torus": len(tori), "cone": len(cones), **other},
    }


def assembly_checks(instances, near=1.0):
    res = {"interferences": [], "contacts": [], "near": [], "fits": []}
    boxes = []
    for ins in instances:
        b = Bnd_Box(); BRepBndLib.Add_s(ins["shape"], b, False); b.Enlarge(near)
        boxes.append(b)
    cyl_cache = {}

    def gcyl(i):
        if i not in cyl_cache:
            cyl_cache[i] = analyze_faces(instances[i]["shape"])[0]
        return cyl_cache[i]

    for i in range(len(instances)):
        for j in range(i + 1, len(instances)):
            if boxes[i].IsOut(boxes[j]):
                continue
            A, B = instances[i], instances[j]
            pair = f"{A['path']}  ↔  {B['path']}"
            com = BRepAlgoAPI_Common(A["shape"], B["shape"])
            vol = 0.0
            if com.IsDone():
                g = GProp_GProps(); BRepGProp.VolumeProperties_s(com.Shape(), g); vol = g.Mass()
            dist = BRepExtrema_DistShapeShape(A["shape"], B["shape"])
            dmin = dist.Value() if dist.IsDone() else None
            if vol > MIN_INTERFERENCE_MM3:
                bb = Bnd_Box(); BRepBndLib.Add_s(com.Shape(), bb, False)
                res["interferences"].append({"pair": pair, "a": A["path"], "b": B["path"], "volume_mm3": round(vol, 3),
                                             "bbox_mm": [round(v, 2) for v in bb.Get()]})
            elif dmin is not None and (dmin < 1e-3 or vol > TOL):
                res["contacts"].append({"pair": pair})
            elif dmin is not None and dmin < near:
                res["near"].append({"pair": pair, "min_gap_mm": round(dmin, 4)})
            # accoppiamenti cilindrici coassiali (foro di una parte / albero dell'altra)
            for X, Y, nx, ny in ((i, j, A, B), (j, i, B, A)):
                for h in gcyl(X):
                    if h["internal"] is not True:
                        continue
                    for s_ in gcyl(Y):
                        if s_["internal"] is not False:
                            continue
                        if abs(abs(dot(h["d"], s_["d"])) - 1) > 1e-4:
                            continue
                        foot = line_foot(s_["o"], h["o"], h["d"])
                        if norm(sub(s_["o"], foot)) > 0.05:
                            continue
                        # sovrapposizione assiale
                        hd = h["d"]
                        h0, h1 = sorted(dot(sub(pp, h["o"]), hd) for pp in (h["p0"], h["p1"]))
                        s0, s1 = sorted(dot(sub(pp, h["o"]), hd) for pp in (s_["p0"], s_["p1"]))
                        ov = min(h1, s1) - max(h0, s0)
                        if ov <= 0.01:
                            continue
                        clr = 2 * h["r"] - 2 * s_["r"]
                        if abs(clr) > 3:  # troppo diversi: non è un accoppiamento
                            continue
                        th = thread_guess(2 * s_["r"], 2 * h["r"])
                        res["fits"].append({"hole_part": nx["path"], "shaft_part": ny["path"],
                                            "hole_dia": round(2 * h["r"], 3), "shaft_dia": round(2 * s_["r"], 3),
                                            "diametral_clearance": round(clr, 3), "engagement_len": round(ov, 3),
                                            "likely_thread": th})
    # deduplica accoppiamenti
    seen, fits = set(), []
    for f in res["fits"]:
        k = (f["hole_part"], f["shaft_part"], f["hole_dia"], f["shaft_dia"])
        if k in seen:
            continue
        seen.add(k); fits.append(f)
    res["fits"] = sorted(fits, key=lambda f: f["diametral_clearance"])
    # spiega le interferenze: filettature non modellate vs interferenze reali
    for it in res["interferences"]:
        rel = [f for f in res["fits"] if {f["hole_part"], f["shaft_part"]} == {it["a"], it["b"]} and f["diametral_clearance"] < -1e-3]
        th = [f for f in rel if f["likely_thread"]]
        real = [f for f in rel if not f["likely_thread"]]
        it["explained_by_thread"] = [f"{f['likely_thread']} (albero Ø{f['shaft_dia']} in foro Ø{f['hole_dia']}, L={f['engagement_len']})" for f in th]
        it["real_overlaps"] = [f"albero Ø{f['shaft_dia']} ({f['shaft_part']}) in foro Ø{f['hole_dia']} ({f['hole_part']}), L={f['engagement_len']}" for f in real]
        it["status"] = "reale" if real or not th else "filettatura non modellata"
    return res


def write_summary(d, path):
    L = [f"# {d['source']}", "", f"Sistema d'origine: {d['originating_system']}", ""]
    L.append("## Struttura")
    for t in d["tree"]:
        L.append("  " * t["depth"] + f"- {t['name']} ({t['type']})")
    L += ["", "## Parti"]
    for pid, p in d["parts"].items():
        f = p["features"]; pr = p["props"]
        if pr["volume_mm3"] < 1e-6:
            L.append(f"### {p['name']} — corpo senza volume (curva o superficie esportata), ignorato"); L.append(""); continue
        L.append(f"### {p['name']}  (istanze: {p['instances']})")
        L.append(f"- ingombro {pr['size_mm']} mm, volume {pr['volume_mm3']:.0f} mm³" +
                 (f", massa {p['mass_kg']} kg (ρ={d['density']} g/cm³)" if p.get("mass_kg") else ""))
        if f["main_axis"]:
            L.append(f"- asse principale {f['main_axis']['dir']} — di rivoluzione: {'sì' if f['is_revolved'] else 'no'}")
        if f["axial_profile"]:
            L.append("- profilo assiale (da→a, Ø, interno/esterno):")
            for e in f["axial_profile"]:
                L.append(f"  - {e['from']:8.3f} → {e['to']:8.3f}  Ø{e['dia']:<8} {'INT' if e['internal'] else 'EST'}  L={e['len']}")
        if f["axial_planes"]:
            L.append(f"- facce piane ⟂ asse a: {f['axial_planes']}")
        for pt in f["hole_patterns_parallel"]:
            L.append(f"- {pt['count']}× Ø{pt['dia']} {'fori' if pt['internal'] else 'perni'} paralleli all'asse, PCD {pt['pcd']}, angoli {pt['angles_deg']}, prof. {pt['len']}")
        for h in f["radial_holes"]:
            L.append(f"- foro radiale Ø{h['dia']} L={h['len']} asse {h['axis_dir']} @ {h['axis_point']}")
        for h in f["other_cylinders"]:
            L.append(f"- altro cilindro Ø{h['dia']} {'INT' if h['internal'] else 'EST'} L={h['len']} asse {h['axis_dir']}")
        if f["fillet_radii"]:
            L.append(f"- raggi di raccordo (tori): {f['fillet_radii']}")
        for c in f["cones"]:
            L.append(f"- cono: semi-angolo {c['half_angle_deg']}°, Ø rif. {c['ref_dia']}{' (sull’asse)' if c['on_main_axis'] else ''}")
        if f["min_radial_walls"]:
            w = f["min_radial_walls"][0]
            L.append(f"- parete radiale minima {w['wall']} mm (Ø{w['ext_dia']} est / Ø{w['int_dia']} int, da {w['from']} a {w['to']})")
        L.append(f"- facce: {f['face_counts']}")
        L.append("")
    a = d.get("assembly")
    if a:
        L.append("## Controlli d'assieme")
        L.append(f"- interferenze: {len(a['interferences'])}")
        for x in a["interferences"]:
            L.append(f"  - **{x['pair']}**: {x['volume_mm3']} mm³ — {x['status'].upper()}")
            for t in x["explained_by_thread"]:
                L.append(f"    - filettatura probabile: {t}")
            for t in x["real_overlaps"]:
                L.append(f"    - **sovrapposizione non spiegata da filettatura**: {t}")
        L.append(f"- contatti: {len(a['contacts'])}")
        for x in a["contacts"]:
            L.append(f"  - {x['pair']}")
        L.append(f"- giochi < 1 mm: {len(a['near'])}")
        for x in a["near"]:
            L.append(f"  - {x['pair']}: {x['min_gap_mm']} mm")
        L.append(f"- accoppiamenti cilindrici coassiali: {len(a['fits'])}")
        for x in a["fits"]:
            th = f"  → probabile {x['likely_thread']}" if x.get("likely_thread") else ""
            L.append(f"  - foro Ø{x['hole_dia']} ({x['hole_part']}) / albero Ø{x['shaft_dia']} ({x['shaft_part']}): gioco diam. {x['diametral_clearance']} mm, impegno {x['engagement_len']} mm{th}")
    with open(path, "w") as fh:
        fh.write("\n".join(L) + "\n")


def jsonable(o):
    if isinstance(o, dict):
        return {k: jsonable(v) for k, v in o.items() if k != "shape"}
    if isinstance(o, (list, tuple)):
        return [jsonable(v) for v in o]
    return o


def process(path, out, density=None):
    name = re.sub(r"^[0-9a-f]{8}-", "", os.path.splitext(os.path.basename(path))[0])
    od = os.path.join(out, name); os.makedirs(od, exist_ok=True)
    head = open(path, errors="ignore").read(4000)
    m = re.search(r"originating_system \*/\s*'([^']*)'", head)
    tree, parts, inst = read_step(path)
    counts = defaultdict(int)
    for i in inst:
        counts[i["part_id"]] += 1
    pdata = {}
    for pid, p in parts.items():
        pr = props(p["shape"])
        e = {"name": p["name"], "instances": counts[pid], "props": pr, "features": part_features(p["shape"])}
        if density:
            e["mass_kg"] = round(pr["volume_mm3"] * density / 1e6, 4)
        pdata[pid] = e
    d = {"source": os.path.basename(path), "originating_system": m.group(1) if m else "?", "density": density,
         "tree": tree, "parts": pdata,
         "instances": [{"part_id": i["part_id"], "path": i["path"], "props": props(i["shape"])} for i in inst]}
    if len(inst) > 1:
        d["assembly"] = assembly_checks(inst)
    with open(os.path.join(od, "step.json"), "w") as fh:
        json.dump(jsonable(d), fh, ensure_ascii=False, indent=1)
    write_summary(d, os.path.join(od, "summary.md"))
    return d


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("steps", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--density", type=float, default=None, help="g/cm3 per calcolare la massa")
    a = ap.parse_args()
    for p in a.steps:
        d = process(p, a.out, a.density)
        extra = ""
        if "assembly" in d:
            A = d["assembly"]
            extra = f", interferenze={len(A['interferences'])}, contatti={len(A['contacts'])}, accoppiamenti={len(A['fits'])}"
        print(f"{d['source']}: parti={len(d['parts'])}, istanze={len(d['instances'])}{extra}")
