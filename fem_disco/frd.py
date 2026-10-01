"""Lettore minimale di file .frd di CalculiX (risultati nodali ASCII)."""
import numpy as np


def read_frd(path):
    nodes, blocks = {}, []
    with open(path) as f:
        lines = f.readlines()
    i = 0
    cur = None
    while i < len(lines):
        L = lines[i]
        if L.startswith("    2C"):
            i += 1
            while not lines[i].startswith(" -3"):
                s = lines[i]
                nodes[int(s[3:13])] = (float(s[13:25]), float(s[25:37]), float(s[37:49]))
                i += 1
        elif L.startswith("  100C"):
            t = float(L[12:24])
            step = int(L[58:63]) if len(L) > 63 else 0
            i += 1
            name = lines[i][5:13].strip()
            comps = []
            i += 1
            while lines[i].startswith(" -5"):
                comps.append(lines[i][5:13].strip())
                i += 1
            ids, vals = [], []
            while not lines[i].startswith(" -3"):
                s = lines[i]
                if s.startswith(" -1"):
                    ids.append(int(s[3:13]))
                    v = [float(s[13 + 12 * k:25 + 12 * k]) for k in range((len(s.rstrip("\n")) - 13) // 12)]
                    vals.append(v)
                elif s.startswith(" -2"):
                    v = [float(s[13 + 12 * k:25 + 12 * k]) for k in range((len(s.rstrip("\n")) - 13) // 12)]
                    vals[-1].extend(v)
                i += 1
            nc = min(len(v) for v in vals) if vals else 0
            blocks.append(dict(name=name, time=t, step=step, comps=comps,
                               ids=np.array(ids), vals=np.array([v[:nc] for v in vals])))
        i += 1
    return nodes, blocks
