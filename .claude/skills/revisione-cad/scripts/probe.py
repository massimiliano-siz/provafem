#!/usr/bin/env python3
"""Misure puntuali su uno STEP, per verificare un dubbio emerso dall'analisi.

Uso:
  probe.py <file.step> --part "<nome>" sections --axis z --at -199 -150 -100
      diametro/ingombro della sezione piana a quelle quote (utile per pezzi con superfici libere)
  probe.py <file.step> --part "<nome>" clearance --point x y z
      distanza minima tra un punto e la superficie della parte (es. parete tra foro e esterno)
  probe.py <file.step> --part "<nome>" faces
      elenco completo delle facce con tipo, dimensioni e posizione
Unità: mm, coordinate del file.
"""
import argparse, os, sys

sys.path.insert(0, os.path.dirname(__file__))
from step_analyze import read_step, analyze_faces  # noqa: E402

from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
from OCP.gp import gp_Pln, gp_Pnt, gp_Dir
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
from OCP.BRepExtrema import BRepExtrema_DistShapeShape


def pick(parts, name):
    for p in parts.values():
        if name is None or p["name"].lower() == name.lower():
            return p
    names = ", ".join(p["name"] for p in parts.values())
    sys.exit(f"Parte '{name}' non trovata. Parti: {names}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("step"); ap.add_argument("--part")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s1 = sub.add_parser("sections"); s1.add_argument("--axis", default="z", choices="xyz"); s1.add_argument("--at", type=float, nargs="+", required=True)
    s2 = sub.add_parser("clearance"); s2.add_argument("--point", type=float, nargs=3, required=True)
    sub.add_parser("faces")
    a = ap.parse_args()
    _, parts, _ = read_step(a.step)
    p = pick(parts, a.part); sh = p["shape"]
    if a.cmd == "sections":
        n = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}[a.axis]
        for v in a.at:
            o = [0, 0, 0]; o["xyz".index(a.axis)] = v
            s = BRepAlgoAPI_Section(sh, gp_Pln(gp_Pnt(*o), gp_Dir(*n))); s.Build()
            b = Bnd_Box(); BRepBndLib.AddOptimal_s(s.Shape(), b, False, False)
            if b.IsVoid():
                print(f"{a.axis}={v}: nessuna sezione"); continue
            x0, y0, z0, x1, y1, z1 = b.Get()
            print(f"{a.axis}={v}: ingombro sezione x {x1-x0:.2f} · y {y1-y0:.2f} · z {z1-z0:.2f} mm")
    elif a.cmd == "clearance":
        v = BRepBuilderAPI_MakeVertex(gp_Pnt(*a.point)).Vertex()
        d = BRepExtrema_DistShapeShape(v, sh)
        print(f"distanza minima dal punto alla superficie: {d.Value():.3f} mm")
    else:
        cyl, planes, tori, cones, other = analyze_faces(sh)
        for c in cyl:
            print(f"cilindro Ø{2*c['r']:.3f} {'INT' if c['internal'] else 'EST'} da {[round(x,2) for x in c['p0']]} a {[round(x,2) for x in c['p1']]}")
        for t in tori:
            print(f"toro R{t['R']:.3f} r{t['r']:.3f}")
        for c in cones:
            print(f"cono semi-angolo {c['half_angle_deg']:.2f}° Ø rif {2*c['ref_r']:.3f}")
        print(f"piani: {len(planes)}; altre: {other}")


if __name__ == "__main__":
    main()
