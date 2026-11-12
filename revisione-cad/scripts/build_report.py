#!/usr/bin/env python3
"""Assembla il report HTML (artifact) da report.json + estrazioni.

Uso: build_report.py report.json --out report.html

report.json:
{
  "meta": {"title", "kind", "lead", "preview"?, "sources": [..]},
  "sheets": [{"id": "SIZ-PRT-0085", "code": "SIZ-PRT-0085", "name": "Pitot Ogive", "pdf_dir": "work/pdf/SIZ-PRT-0085"}],
  "findings": [{"id": "F1", "sheet": "SIZ-PRT-0085" | null, "x": 0.31, "y": 0.62, "kind": "err|prog|quota|datum|gdt|ok",
                "title", "body", "change": [{"label","was","now"}], "refs": ["F2"], "parts": ["i3"],
                "confidence": "alta|media|bassa", "source": "PDF ↔ STEP"}],
  "mesh": "work/mesh.json" | null,
  "context_dirs": ["work/pdf/...", "work/step/..."]     # i summary.md finiscono nel contesto della chat
}
I percorsi relativi sono risolti rispetto alla cartella di report.json.
"""
import argparse, base64, json, os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "..", "assets", "template.html")
KINDS = {"err", "prog", "quota", "datum", "gdt", "ok"}


def png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    w, h = struct.unpack(">II", head[16:24])
    return w, h


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("report"); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    base = os.path.dirname(os.path.abspath(a.report))
    rp = lambda p: p if os.path.isabs(p) else os.path.join(base, p)
    R = json.load(open(a.report))
    problems = []
    ids = {f["id"] for f in R.get("findings", [])}
    sheet_ids = {s["id"] for s in R.get("sheets", [])}
    for f in R.get("findings", []):
        if f.get("kind") not in KINDS:
            problems.append(f"{f['id']}: kind '{f.get('kind')}' non valido")
        if f.get("sheet") and f["sheet"] not in sheet_ids:
            problems.append(f"{f['id']}: foglio '{f['sheet']}' inesistente")
        for r in f.get("refs", []):
            if r not in ids:
                problems.append(f"{f['id']}: rimando a '{r}' inesistente")
        if f.get("sheet") and (f.get("x") is None or f.get("y") is None):
            problems.append(f"{f['id']}: manca la posizione x,y sul foglio")
    # fogli: immagine incorporata + cartiglio estratto
    for s in R.get("sheets", []):
        d = rp(s.pop("pdf_dir"))
        png = os.path.join(d, "sheet.png")
        s["w"], s["h"] = png_size(png)
        s["img"] = "data:image/png;base64," + base64.b64encode(open(png, "rb").read()).decode()
        t = json.load(open(os.path.join(d, "text.json")))
        tb = {k: v for k, v in t.get("title_block", {}).items() if not k.startswith("_") and v}
        s["title_block"] = {**tb, **s.get("title_block", {})}
    # modello 3D
    mesh = R.pop("mesh", None)
    if mesh:
        M = json.load(open(rp(mesh)))
        R["model"] = M
        inst = {i["id"] for i in M["instances"]}
        for f in R.get("findings", []):
            for p in f.get("parts", []):
                if p not in inst:
                    problems.append(f"{f['id']}: parte '{p}' non presente nel modello 3D")
    # contesto per la chat
    ctx = []
    for d in R.pop("context_dirs", []):
        sm = os.path.join(rp(d), "summary.md")
        if os.path.exists(sm):
            ctx.append(open(sm).read())
    R["context_text"] = "\n\n".join(ctx)[:120000]
    # titolo e introduzione: generici, ricavati da ciò che è stato caricato
    m = R.setdefault("meta", {})
    m.setdefault("kind", "Revisione CAD")
    if not m.get("title"):
        names = [s_.get("name") or s_["code"] for s_ in R.get("sheets", [])]
        proj = m.get("project")
        m["title"] = proj or ("Revisione CAD" if not names else
                              (names[0] if len(names) == 1 else f"{names[0]} e altri {len(names) - 1}"))
    if not m.get("lead"):
        n_sh = len(R.get("sheets", [])); has3d = bool(R.get("model"))
        parts = []
        if n_sh:
            parts.append(f"{n_sh} disegn{'o' if n_sh == 1 else 'i'}")
        if has3d:
            parts.append("modello 3D" + (" dell'assieme" if len(R["model"]["instances"]) > 1 else ""))
        m["lead"] = ("Analizzati: " + " e ".join(parts) + ". " if parts else "") + \
            "Rosso: errori sul disegno. Ambra: modifiche di progetto. Blu: indicazioni mancanti. Verde: controlli superati."
    if problems:
        print("ATTENZIONE:\n  " + "\n  ".join(problems), file=sys.stderr)
    html = open(TEMPLATE).read()
    data = json.dumps(R, ensure_ascii=False).replace("</", "<\\/")
    title = R["meta"]["title"].replace("<", "&lt;")
    if R["meta"].get("kind") and "CAD" not in title:
        title = title + " · Revisione CAD"
    html = html.replace("__TITLE__", title).replace("__REPORT_JSON__", data)
    with open(a.out, "w") as fh:
        fh.write(html)
    print(f"{a.out}: {len(html)/1e6:.2f} MB, {len(R.get('findings', []))} voci, {len(R.get('sheets', []))} fogli"
          + (", 3D sì" if R.get("model") else ""))
    if len(html) > 15.5e6:
        print("ATTENZIONE: oltre il limite di 16 MB dell'artifact", file=sys.stderr)


if __name__ == "__main__":
    main()
