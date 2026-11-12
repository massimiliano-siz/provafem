#!/usr/bin/env python3
"""Tassella uno STEP (parte o assieme) per il viewer 3D del report.

Uso: step_mesh.py <file.step> --out mesh.json [--defl 0.25] [--max-mb 6]

Output: {"unit":"mm","bbox":[...],"instances":[{"id","name","path","color","pos":b64(Float32),"idx":b64(Uint32)}]}
Le coordinate sono globali (posizione nell'assieme già applicata).
"""
import argparse, base64, json, os, sys
from array import array

sys.path.insert(0, os.path.dirname(__file__))
from step_analyze import read_step  # noqa: E402

from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
from OCP.TopoDS import TopoDS
from OCP.BRep import BRep_Tool
from OCP.TopLoc import TopLoc_Location
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib

PALETTE = ["#8FA3B3", "#D9A441", "#5B8DEF", "#4FB286", "#C9785D", "#9C7FD1", "#6CB6C9", "#B5B86A", "#D17FA6", "#7F8C99"]


def tessellate(shape, lin, ang):
    BRepMesh_IncrementalMesh(shape, lin, False, ang, True)
    pos, idx = array("f"), array("I")
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        f = TopoDS.Face_s(exp.Current()); exp.Next()
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(f, loc)
        if tri is None:
            continue
        tr = loc.Transformation()
        base = len(pos) // 3
        for i in range(1, tri.NbNodes() + 1):
            p = tri.Node(i).Transformed(tr)
            pos.extend((p.X(), p.Y(), p.Z()))
        rev = f.Orientation() == TopAbs_REVERSED
        for i in range(1, tri.NbTriangles() + 1):
            a, b, c = tri.Triangle(i).Get()
            if rev:
                b, c = c, b
            idx.extend((base + a - 1, base + b - 1, base + c - 1))
    return pos, idx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("step"); ap.add_argument("--out", required=True)
    ap.add_argument("--defl", type=float, default=0.25, help="deflessione lineare relativa (mm per pezzi piccoli)")
    ap.add_argument("--max-mb", type=float, default=6.0)
    a = ap.parse_args()
    tree, parts, inst = read_step(a.step)
    defl = a.defl
    for attempt in range(5):
        out, total = [], 0
        bb = Bnd_Box()
        colors = {}
        for n, ins in enumerate(inst):
            b = Bnd_Box(); BRepBndLib.Add_s(ins["shape"], b, False); bb.Add(b)
            x0, y0, z0, x1, y1, z1 = b.Get()
            diag = ((x1 - x0) ** 2 + (y1 - y0) ** 2 + (z1 - z0) ** 2) ** 0.5
            lin = max(0.02, defl * diag / 100)  # deflessione proporzionale alla dimensione
            pos, idx = tessellate(ins["shape"], lin, 0.35)
            if ins["part_id"] not in colors:
                colors[ins["part_id"]] = PALETTE[len(colors) % len(PALETTE)]
            pb, ib = base64.b64encode(pos.tobytes()).decode(), base64.b64encode(idx.tobytes()).decode()
            total += len(pb) + len(ib)
            out.append({"id": f"i{n}", "part_id": ins["part_id"], "name": ins["name"], "path": ins["path"],
                        "color": colors[ins["part_id"]], "pos": pb, "idx": ib, "tris": len(idx) // 3})
        if total / 1e6 <= a.max_mb:
            break
        defl *= 2
    d = {"unit": "mm", "bbox": [round(v, 3) for v in bb.Get()], "instances": out}
    with open(a.out, "w") as fh:
        json.dump(d, fh)
    print(f"{len(out)} istanze, {sum(o['tris'] for o in out)} triangoli, {total/1e6:.2f} MB (defl {defl})")


if __name__ == "__main__":
    main()
