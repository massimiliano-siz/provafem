#!/usr/bin/env python3
"""Estrae testi (con posizione e rotazione), note, cartiglio e immagini da disegni PDF.

Uso: pdf_extract.py <file.pdf> [...] --out <dir>

Per ogni foglio produce:
  <out>/<nome>/sheet.png          foglio intero (per l'artifact)
  <out>/<nome>/tiles/*.png        riquadri ad alta risoluzione (per la lettura in visione)
  <out>/<nome>/text.json          testi raggruppati, con bbox in pt e normalizzata 0..1
  <out>/<nome>/summary.md         riassunto leggibile

Richiede PDF esportati con testo selezionabile (Onshape: Export > Text = Selectable).
"""
import argparse, json, math, os, re, subprocess, sys
from collections import defaultdict

import pdfplumber

SHEET_DPI = 150
TILE_DPI = 300
TILE_GRID = (3, 2)  # colonne x righe

DIM_RE = re.compile(
    r"(^|\s)(\d+X\s*)?([ØR⌀]\s*\d|M\d+|\d+/\d+\s*[-−]|\d+[,.]?\d*\s*(±|\+|−|-)?\s*\d*[,.]?\d*$|\d+[,.]?\d*°)"
)
SPACE_FIX = re.compile(r"([ØR⌀])\s+(?=\d)")
THREAD_RE = re.compile(r"\bM\d+(?:[,.]\d+)?(?:\s*[xX×]\s*\d+(?:[,.]\d+)?)?|\b\d+/\d+\s*[-−]\s*\d+\s*(?:G|NPT|UNC|UNF|BSP\w*)?")
WATERMARK_WORDS = {"PRELIMINARY", "DRAWING", "PRELIMINARYDRAWING", "DRAFT", "PRELIMINARY DRAWING"}


def char_frame(c, page_h):
    a, b, cc, d, e, f = c["matrix"]
    ang = math.degrees(math.atan2(b, a))
    ang = round(ang / 1.0) * 1.0
    r = math.radians(ang)
    ux, uy = math.cos(r), math.sin(r)
    u = e * ux + f * uy
    v = -e * uy + f * ux
    size = math.hypot(a, b) or c.get("size", 5)
    return ang, u, v, size


def group_text(chars, page_h):
    """Raggruppa i caratteri in stringhe rispettando rotazione e corpo del testo."""
    buckets = defaultdict(list)
    for c in chars:
        if not c["text"]:
            continue
        ang, u, v, size = char_frame(c, page_h)
        buckets[(ang, round(size, 1))].append((v, u, size, c))
    runs = []
    for (ang, size), items in buckets.items():
        items.sort(key=lambda t: t[0])
        lines, cur, lv = [], [], None
        for t in items:
            if cur and abs(t[0] - lv) > size * 0.35:
                lines.append(cur); cur = []
            cur.append(t); lv = t[0]
        if cur:
            lines.append(cur)
        for ln in lines:
            ln.sort(key=lambda t: t[1])
            run, last_end = [], None
            for v, u, sz, c in ln:
                gap = (u - last_end) if last_end is not None else 0
                if run and gap > sz * 0.75:
                    runs.append((ang, run)); run = []
                    gap = 0
                if c["text"] == " ":
                    if run and run[-1]["text"] != " ":
                        run.append(c)
                    last_end = u + sz * 0.26
                    continue
                if run and gap > sz * 0.18 and run[-1]["text"] != " ":
                    run.append({**c, "text": " "})
                run.append(c)
                # avanzamento del glifo lungo la linea di base
                w = (c["x1"] - c["x0"]) if ang % 180 == 0 else (c["bottom"] - c["top"]) if ang % 90 == 0 else sz * 0.62
                last_end = u + w
            if run:
                runs.append((ang, run))
    out = []
    for ang, cs in runs:
        text = SPACE_FIX.sub(r"\1", "".join(c["text"] for c in cs).strip())
        if not text:
            continue
        cs = [c for c in cs if c["text"] != " "] or cs
        x0 = min(c["x0"] for c in cs); x1 = max(c["x1"] for c in cs)
        t0 = min(c["top"] for c in cs); t1 = max(c["bottom"] for c in cs)
        fonts = sorted({c["fontname"].split("+")[-1] for c in cs})
        out.append({
            "text": text,
            "rot": int(ang) % 360,
            "bbox": [round(x0, 2), round(t0, 2), round(x1, 2), round(t1, 2)],
            "size": round(max(c.get("size", 0) for c in cs), 2),
            "fonts": fonts,
        })
    return out


def find_cell(bbox, hsegs, vsegs):
    """Cella della tabella che contiene bbox, ricavata dalle linee vettoriali."""
    x0, t0, x1, t1 = bbox
    cx, cy = (x0 + x1) / 2, (t0 + t1) / 2
    left = max((x for x, a, b in vsegs if x <= x0 + 0.5 and a <= cy <= b), default=None)
    right = min((x for x, a, b in vsegs if x >= x1 - 0.5 and a <= cy <= b), default=None)
    top = max((y for y, a, b in hsegs if y <= t0 + 0.5 and a <= cx <= b), default=None)
    bot = min((y for y, a, b in hsegs if y >= t1 - 0.5 and a <= cx <= b), default=None)
    if None in (left, right, top, bot):
        return None
    return [left, top, right, bot]


def segments(page):
    hs, vs = [], []
    for l in page.lines + [e for r in page.rects for e in ()]:
        x0, x1, t0, t1 = l["x0"], l["x1"], l["top"], l["bottom"]
        if abs(t1 - t0) < 0.6 and x1 - x0 > 3:
            hs.append(((t0 + t1) / 2, min(x0, x1), max(x0, x1)))
        elif abs(x1 - x0) < 0.6 and t1 - t0 > 3:
            vs.append(((x0 + x1) / 2, min(t0, t1), max(t0, t1)))
    return hs, vs


def inside(b, cell, pad=0.5):
    return b[0] >= cell[0] - pad and b[2] <= cell[2] + pad and b[1] >= cell[1] - pad and b[3] <= cell[3] + pad


TB_LABELS = {"TITLE": "title", "DWG NO.": "dwg_no", "SIZE": "size", "SCALE": "scale", "WEIGHT": "weight",
             "SHEET": "sheet", "REV.": "rev", "MATERIAL": "material", "TREATMENT": "treatment"}


def classify(items, W, H, page):
    hs, vs = segments(page)
    sizes = sorted(i["size"] for i in items) or [5]
    med = sizes[len(sizes) // 2]
    for it in items:
        it["kind"] = "text"
        t = it["text"].replace(" ", "").upper()
        if t in {w.replace(" ", "") for w in WATERMARK_WORDS} or (it["rot"] % 90 != 0 and it["size"] > 2.2 * med):
            it["kind"] = "watermark"
    # lettere singole della filigrana (stesso angolo obliquo, corpo grande)
    for it in items:
        if it["kind"] == "text" and it["rot"] % 90 != 0 and it["size"] > 2.2 * med:
            it["kind"] = "watermark"
    for it in items:
        x0, t0, x1, t1 = it["bbox"]
        if it["kind"] == "text" and re.fullmatch(r"[A-H1-9]", it["text"]) and (
                t0 < 0.04 * H or t1 > 0.96 * H or x0 < 0.03 * W or x1 > 0.97 * W):
            it["kind"] = "grid"
    # cartiglio: tutto ciò che sta nel riquadro delimitato dalle etichette note
    anchors = [i for i in items if i["text"] in TB_LABELS or i["text"].upper().startswith("UNLESS OTHERWISE")]
    tb_box = None
    if anchors:
        tb_box = [min(i["bbox"][0] for i in anchors) - 2, min(i["bbox"][1] for i in anchors) - 2, W, H]
    hdr = next((i for i in items if i["text"].upper().startswith("TECHNICAL NOTES")), None)
    notes_box = None
    if hdr:
        hdr["kind"] = "notes_header"
        long_h = [h for h in hs if h[2] - h[1] > 120]
        cell = find_cell(hdr["bbox"], long_h, vs)
        notes_box = cell or [hdr["bbox"][0] - 5, hdr["bbox"][1], W, tb_box[1] if tb_box else H]
    rev = next((i for i in items if i["text"] == "REVISIONS"), None)
    rev_box = None
    if rev:
        # la tabella revisioni: dalla cella del titolo fino a due righe sotto
        c = find_cell(rev["bbox"], hs, vs)
        if c:
            below = sorted({round(y, 1) for y, a, b in hs if y > c[3] + 1 and a <= c[0] + 2 and b >= c[2] - 2})
            rev_box = [c[0], c[1], c[2], below[1] if len(below) > 1 else (below[0] if below else c[3] + 40)]
    for it in items:
        if it["kind"] != "text":
            continue
        b = it["bbox"]
        if notes_box and inside(b, notes_box, 2):
            it["kind"] = "note"
        elif rev_box and inside(b, rev_box, 2):
            it["kind"] = "revisions"
        elif tb_box and b[0] >= tb_box[0] and b[1] >= tb_box[1]:
            it["kind"] = "title_block"
    for it in items:
        if it["kind"] != "text":
            continue
        t = it["text"]
        if THREAD_RE.search(t) or re.search(r"[Ø⌀↧⌴⌵]|THRU|TAPPED|\d+X\b", t):
            it["kind"] = "callout"
        elif re.fullmatch(r"[ØR⌀]?\s*\d+(?:[,.]\d+)?\s*(?:°)?(?:\s*[±+−-]\s*\d+(?:[,.]\d+)?)?", t):
            it["kind"] = "dimension"
        elif re.fullmatch(r"[A-Z](?:\s*-\s*[A-Z])?", t):
            it["kind"] = "label"
    return items, hs, vs


GDT_SYMBOLS = set("⏤⏥○⌭⌒⌓⟂⊥∠∥⌖◎↗⌰≡")


def merge_gdt(items):
    """Ricompone i riquadri di tolleranza geometrica: simbolo + valore + riferimenti."""
    out, used = [], set()
    for i, it in enumerate(items):
        if it["text"] and it["text"][0] in GDT_SYMBOLS and len(it["text"]) <= 2 and it["kind"] not in ("note", "title_block"):
            x0, t0, x1, t1 = it["bbox"]; cy = (t0 + t1) / 2
            parts = [it]
            for j, o in enumerate(items):
                if j == i or j in used or o["kind"] in ("note", "title_block", "watermark", "grid"):
                    continue
                ox0, ot0, ox1, ot1 = o["bbox"]
                if abs((ot0 + ot1) / 2 - cy) < 4 and 0 <= ox0 - parts[-1]["bbox"][2] < 14:
                    parts.append(o); used.add(j)
            used.add(i)
            txt = " | ".join(p["text"] for p in parts)
            bb = [min(p["bbox"][0] for p in parts), min(p["bbox"][1] for p in parts),
                  max(p["bbox"][2] for p in parts), max(p["bbox"][3] for p in parts)]
            out.append({**it, "text": txt, "bbox": bb, "kind": "gdt"})
    return [it for k, it in enumerate(items) if k not in used] + out


def parse_title_block(items, hs, vs):
    tb = [i for i in items if i["kind"] in ("title_block", "revisions")]
    res = {}
    for L in tb:
        key = TB_LABELS.get(L["text"])
        if not key:
            continue
        cell = find_cell(L["bbox"], hs, vs)
        if not cell:
            continue
        vals = [o for o in tb if o is not L and inside(o["bbox"], cell, 1)]
        vals.sort(key=lambda o: (round(o["bbox"][1]), o["bbox"][0]))
        res[key] = " ".join(o["text"] for o in vals)
    # tolleranze generali e altre righe del riquadro sinistro: riportate come righe
    rows = defaultdict(list)
    for o in tb:
        if o["text"] in TB_LABELS:
            continue
        rows[round(o["bbox"][1] / 4)].append(o)
    res["_righe"] = [" | ".join(x["text"] for x in sorted(r, key=lambda o: o["bbox"][0])) for _, r in sorted(rows.items())]
    rv = sorted([i for i in items if i["kind"] == "revisions"], key=lambda o: (round(o["bbox"][1] / 4), o["bbox"][0]))
    res["_revisioni"] = [o["text"] for o in rv]
    return res


def parse_notes(items):
    ns = sorted([i for i in items if i["kind"] == "note"], key=lambda o: (round(o["bbox"][1] / 3), o["bbox"][0]))
    lines = defaultdict(list)
    for o in ns:
        lines[round(o["bbox"][1] / 3)].append(o)
    notes, cur = [], None
    for _, ln in sorted(lines.items()):
        ln.sort(key=lambda o: o["bbox"][0])
        txt = " ".join(o["text"] for o in ln)
        m = re.match(r"^(\d+)\.\s*(.*)", txt)
        if m:
            cur = [m.group(1), m.group(2)]; notes.append(cur)
        elif cur:
            cur[1] += " " + txt
        else:
            notes.append(["", txt])
    return [f"{n}. {t}".strip(". ") if n else t for n, t in notes]


def detect_underlines(items, page):
    """Quote forzate: Onshape le sottolinea se 'Overridden dimensions = Show underlines'."""
    segs = []
    for l in page.lines:
        segs.append((l["x0"], l["top"], l["x1"], l["bottom"]))
    for e in page.edges if hasattr(page, "edges") else []:
        pass
    flagged = []
    for it in items:
        if it["kind"] not in ("dimension", "callout"):
            continue
        x0, t0, x1, t1 = it["bbox"]
        w = x1 - x0; h = t1 - t0
        if it["rot"] in (0, 180):
            for sx0, st0, sx1, st1 in segs:
                if abs(st1 - st0) < 0.3 and 0 < st0 - t1 < 2.5 and abs(min(sx0, sx1) - x0) < 1.5 and abs(max(sx0, sx1) - x1) < 1.5:
                    flagged.append(it); it["underlined"] = True; break
        else:
            for sx0, st0, sx1, st1 in segs:
                if abs(sx1 - sx0) < 0.3 and (0 < sx0 - x1 < 2.5 or 0 < x0 - sx0 < 2.5) and abs(st0 - t0) < 1.5 and abs(st1 - t1) < 1.5:
                    flagged.append(it); it["underlined"] = True; break
    return flagged


def render(pdf, outdir, W, H):
    os.makedirs(os.path.join(outdir, "tiles"), exist_ok=True)
    subprocess.run(["pdftoppm", "-r", str(SHEET_DPI), "-png", "-singlefile", pdf, os.path.join(outdir, "sheet")], check=True)
    cols, rows = TILE_GRID
    pxW = W / 72 * TILE_DPI; pxH = H / 72 * TILE_DPI
    tw = pxW / cols; th = pxH / rows
    ov = 0.08  # sovrapposizione
    tiles = []
    for r in range(rows):
        for c in range(cols):
            x = max(0, int(c * tw - ov * tw)); y = max(0, int(r * th - ov * th))
            w = int(min(pxW - x, tw * (1 + 2 * ov))); h = int(min(pxH - y, th * (1 + 2 * ov)))
            name = f"r{r}c{c}"
            subprocess.run(["pdftoppm", "-r", str(TILE_DPI), "-png", "-singlefile", "-x", str(x), "-y", str(y),
                            "-W", str(w), "-H", str(h), pdf, os.path.join(outdir, "tiles", name)], check=True)
            tiles.append({"file": f"tiles/{name}.png", "bbox_norm": [round(x / pxW, 4), round(y / pxH, 4),
                          round((x + w) / pxW, 4), round((y + h) / pxH, 4)]})
    return tiles


def process(pdf, out):
    name = os.path.splitext(os.path.basename(pdf))[0]
    name = re.sub(r"^[0-9a-f]{8}-", "", name)
    outdir = os.path.join(out, name)
    os.makedirs(outdir, exist_ok=True)
    doc = pdfplumber.open(pdf)
    sheets = []
    for pi, page in enumerate(doc.pages):
        W, H = float(page.width), float(page.height)
        items = group_text(page.chars, H)
        items, hs, vs = classify(items, W, H, page)
        items = merge_gdt(items)
        under = detect_underlines(items, page)
        for it in items:
            x0, t0, x1, t1 = it["bbox"]
            it["bbox_norm"] = [round(x0 / W, 4), round(t0 / H, 4), round(x1 / W, 4), round(t1 / H, 4)]
        items.sort(key=lambda i: (i["kind"], i["bbox"][1], i["bbox"][0]))
        tb = parse_title_block(items, hs, vs)
        notes = parse_notes(items)
        sheet_dir = outdir if len(doc.pages) == 1 else os.path.join(outdir, f"p{pi+1}")
        os.makedirs(sheet_dir, exist_ok=True)
        tiles = render(pdf, sheet_dir, W, H) if pi == 0 or True else []
        data = {
            "source": os.path.basename(pdf), "page": pi + 1, "size_pt": [W, H],
            "text_found": len(page.chars) > 0,
            "n_vectors": {"lines": len(page.lines), "curves": len(page.curves)},
            "title_block": tb, "notes": notes,
            "underlined_dims": [i["text"] for i in under],
            "items": items, "sheet_png": "sheet.png", "tiles": tiles,
        }
        with open(os.path.join(sheet_dir, "text.json"), "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        write_summary(data, sheet_dir)
        sheets.append(data)
    return sheets


def write_summary(d, outdir):
    L = [f"# {d['source']} (pag. {d['page']})", ""]
    if not d["text_found"]:
        L += ["**ATTENZIONE: nessun testo estraibile.** Riesportare da Onshape con Text = Selectable,",
              "oppure leggere quote e note in visione dai riquadri in tiles/.", ""]
    L.append("## Cartiglio")
    for k, v in d["title_block"].items():
        if not k.startswith("_"):
            L.append(f"- {k}: {v}")
    L += ["", "Righe del riquadro tolleranze/firme:"] + [f"- {r}" for r in d["title_block"].get("_righe", [])]
    L += ["", "Tabella revisioni: " + " | ".join(d["title_block"].get("_revisioni", []))]
    L += ["", "## Note tecniche"] + [f"- {n}" for n in d["notes"]]
    L += ["", "## Quote e richiami (testo, rotazione, posizione normalizzata x,y)"]
    for it in d["items"]:
        if it["kind"] in ("dimension", "callout", "label", "gdt"):
            x0, y0, x1, y1 = it["bbox_norm"]
            u = "  **[SOTTOLINEATA: quota forzata?]**" if it.get("underlined") else ""
            L.append(f"- `{it['text']}` ({it['kind']}, rot {it['rot']}°, @{(x0+x1)/2:.3f},{(y0+y1)/2:.3f}){u}")
    other = [i for i in d["items"] if i["kind"] == "text"]
    if other:
        L += ["", "## Altri testi"] + [f"- `{i['text']}` @{i['bbox_norm'][0]:.3f},{i['bbox_norm'][1]:.3f}" for i in other]
    with open(os.path.join(outdir, "summary.md"), "w") as f:
        f.write("\n".join(L) + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("pdfs", nargs="+")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    for p in a.pdfs:
        for s in process(p, a.out):
            n_dim = sum(1 for i in s["items"] if i["kind"] in ("dimension", "callout"))
            print(f"{s['source']} p{s['page']}: testo={'sì' if s['text_found'] else 'NO'}, quote/richiami={n_dim}, note={len(s['notes'])}, sottolineate={len(s['underlined_dims'])}")
