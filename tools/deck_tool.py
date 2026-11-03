#!/usr/bin/env python3
"""Add presentations to this repo and rebuild the generated files.

  python tools/deck_tool.py add SOURCE [options]   # SOURCE: a folder or a .zip holding a deck
  python tools/deck_tool.py build                  # rewrite every deck's index.html + deck.js, and catalog.js
  python tools/deck_tool.py list                   # show the decks in the repo

What `add` looks for inside SOURCE (any depth):
  slides      a folder of slide images (slides/s-01.png ...); if there is none, the PDF pages are rendered
              (needs PyMuPDF or poppler's pdftoppm)
  *.pdf       offered as the PDF download
  *.pptx      offered as the PowerPoint download; its speaker notes feed the player's notes panel
  *single_file*.html   offered as the one-file HTML download
  README*.txt kept beside the deck as source_README.txt

Every deck lives in decks/<id>/ with deck.json as its hand-editable source of truth. After editing a
deck.json (title, tags, notes, ...) run `build`. Needs Python 3.8+; Pillow for thumbnails (optional),
python-pptx for speaker notes (optional).
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DECKS = ROOT / "decks"
TEMPLATE = ROOT / "assets" / "templates" / "player.html"
IMG_EXT = {".png", ".jpg", ".jpeg", ".webp"}
THUMB_W = 640
GH_WARN, GH_LIMIT = 50 * 2**20, 100 * 2**20      # GitHub warns above 50 MB and rejects files above 100 MB

try:
    from PIL import Image
except ImportError:                                # thumbnails are skipped without Pillow
    Image = None


# ---------------------------------------------------------------- progress output
def step(i: int, n: int, msg: str) -> None:
    print(f"[{i}/{n}] {msg}", flush=True)


def bar(done: int, total: int, label: str = "") -> None:
    w = 30
    fill = int(w * done / total) if total else w
    end = "\n" if done >= total else ""
    print(f"\r      [{'#' * fill}{'.' * (w - fill)}] {done}/{total} {label}".ljust(78), end=end, flush=True)


def info(msg: str) -> None:
    print(f"      {msg}", flush=True)


def warn(msg: str) -> None:
    print(f"      WARNING: {msg}", flush=True)


def die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------- helpers
def natural_key(p: Path):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", p.name)]


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "deck"


def mb(n: int) -> str:
    return f"{n / 2**20:.1f} MB"


def image_size(p: Path) -> tuple[int, int] | None:
    if Image is not None:
        with Image.open(p) as im:
            return im.size
    if p.suffix.lower() == ".png":                 # PNG header: width/height at bytes 16..24
        with open(p, "rb") as f:
            head = f.read(24)
        if head[:8] == b"\x89PNG\r\n\x1a\n":
            return struct.unpack(">II", head[16:24])
    return None


def html_title(p: Path) -> str | None:
    with open(p, "r", encoding="utf-8", errors="ignore") as f:
        head = f.read(4096)
    m = re.search(r"<title>(.*?)</title>", head, re.S | re.I)
    return html.unescape(m.group(1).strip()) if m else None


def safe_extract(zpath: Path, dest: Path) -> None:
    with zipfile.ZipFile(zpath) as z:
        for m in z.infolist():
            target = (dest / m.filename).resolve()
            if not str(target).startswith(str(dest.resolve())):
                die(f"unsafe path in zip: {m.filename}")
        z.extractall(dest)


def check_size(p: Path) -> None:
    n = p.stat().st_size
    if n > GH_LIMIT:
        die(f"{p.name} is {mb(n)}; GitHub rejects files over 100 MB. Shrink it or use Git LFS.")
    if n > GH_WARN:
        warn(f"{p.name} is {mb(n)}; GitHub warns about files over 50 MB.")


# ---------------------------------------------------------------- discovery
def find_slide_dir(src: Path) -> Path | None:
    cands = []
    for d in [src, *[p for p in src.rglob("*") if p.is_dir()]]:
        imgs = [p for p in d.iterdir() if p.is_file() and p.suffix.lower() in IMG_EXT]
        if len(imgs) >= 2:
            cands.append((d.name.lower() == "slides", len(imgs), d))
    if not cands:
        return None
    cands.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return cands[0][2]


def first(src: Path, pattern: str) -> Path | None:
    hits = sorted(src.rglob(pattern), key=lambda p: (len(p.parts), p.name))
    return hits[0] if hits else None


def render_pdf(pdf: Path, out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(pdf)
        n = doc.page_count
        for i, page in enumerate(doc, 1):
            page.get_pixmap(dpi=150).save(out / f"s-{i:02d}.png")
            bar(i, n, "pages rendered")
        return sorted(out.glob("*.png"), key=natural_key)
    except ImportError:
        pass
    if shutil.which("pdftoppm"):
        info("rendering with pdftoppm ...")
        subprocess.run(["pdftoppm", "-r", "150", "-png", str(pdf), str(out / "s")], check=True)
        return sorted(out.glob("*.png"), key=natural_key)
    die("no slide images found and cannot render the PDF: install PyMuPDF (pip install pymupdf) or poppler")
    return []


def pptx_notes(pptx: Path) -> list[str]:
    try:
        from pptx import Presentation
    except ImportError:
        warn("python-pptx not installed (pip install python-pptx): no speaker notes")
        return []
    pres = Presentation(str(pptx))
    out = []
    for s in pres.slides:
        out.append(s.notes_slide.notes_text_frame.text.strip() if s.has_notes_slide else "")
    return out


def pptx_title(pptx: Path) -> str | None:
    try:
        from pptx import Presentation
        return Presentation(str(pptx)).core_properties.title or None
    except Exception:
        return None


# ---------------------------------------------------------------- add
def cmd_add(a: argparse.Namespace) -> None:
    S = 6
    src_in = Path(a.source).expanduser().resolve()
    if not src_in.exists():
        die(f"not found: {src_in}")

    tmp = None
    step(1, S, f"Reading {src_in.name}")
    if src_in.is_file() and src_in.suffix.lower() == ".zip":
        tmp = Path(tempfile.mkdtemp(prefix="deck_"))
        safe_extract(src_in, tmp)
        src = tmp
        info(f"unzipped to {tmp}")
    elif src_in.is_dir():
        src = src_in
    else:
        die("SOURCE must be a folder or a .zip")

    try:
        step(2, S, "Finding slides and downloads")
        pdf = first(src, "*.pdf")
        pptx = first(src, "*.pptx")
        single = first(src, "*single_file*.html") or first(src, "*single*.html")
        readme = first(src, "README*.txt") or first(src, "README*.md")
        slide_dir = find_slide_dir(src)
        for label, p in (("slides", slide_dir), ("pdf", pdf), ("pptx", pptx), ("html", single), ("readme", readme)):
            info(f"{label:7s}: {p.relative_to(src) if p else '-'}")

        title = a.title
        if not title:
            for cand in [single, slide_dir and slide_dir.parent / "index.html"]:
                if cand and cand.exists():
                    title = html_title(cand)
                    if title:
                        break
        if not title and pptx:
            title = pptx_title(pptx)
        stem = (pdf or pptx or single or src_in).stem
        title = title or stem
        date = a.date or dt.date.today().isoformat()
        deck_id = a.id or f"{a.updated or date}_{slugify(stem)}"
        dest = DECKS / deck_id
        if dest.exists():
            if not a.force:
                die(f"decks/{deck_id} already exists (use --force to replace it, or --id for a new id)")
            shutil.rmtree(dest)
        info(f"id     : {deck_id}")
        info(f"title  : {title}")

        step(3, S, "Copying slide images")
        (dest / "slides").mkdir(parents=True)
        if slide_dir:
            imgs = sorted([p for p in slide_dir.iterdir() if p.is_file() and p.suffix.lower() in IMG_EXT], key=natural_key)
        elif pdf:
            info("no image folder: rendering the PDF")
            imgs = render_pdf(pdf, Path(tempfile.mkdtemp(prefix="pdfpages_")))
        else:
            die("no slide images and no PDF to render them from")
        slides = []
        for i, p in enumerate(imgs, 1):
            out = dest / "slides" / f"s-{i:02d}{p.suffix.lower()}"
            shutil.copy2(p, out)
            slides.append(out)
            bar(i, len(imgs), "slides")
        sizes = {image_size(p) for p in slides} - {None}
        ratios = {round(w / h, 3) for w, h in sizes}
        if len(ratios) > 1:
            warn(f"slides have different aspect ratios: {sorted(ratios)}")
        if len(sizes) > 1:
            info(f"slide pixel sizes vary ({', '.join(f'{w}x{h}' for w, h in sorted(sizes))}); same ratio, fine")

        step(4, S, "Making thumbnails")
        make_thumbs(dest)

        step(5, S, "Copying downloads and reading speaker notes")
        (dest / "downloads").mkdir()
        files = {}
        for kind, p in (("pdf", pdf), ("pptx", pptx), ("html", single)):
            if p:
                check_size(p)
                shutil.copy2(p, dest / "downloads" / p.name)
                files[kind] = f"downloads/{p.name}"
                info(f"{kind:5s} {p.name}  ({mb(p.stat().st_size)})")
        if readme:
            shutil.copy2(readme, dest / ("source_README" + readme.suffix))
        notes = pptx_notes(pptx) if pptx else []
        if notes:
            info(f"notes on {sum(1 for n in notes if n)} of {len(notes)} slides")
            if len(notes) != len(slides):
                warn(f"PPTX has {len(notes)} slides but {len(slides)} images were found; notes are matched by position")

        step(6, S, "Writing deck.json, index.html, deck.js, catalog.js")
        w, h = next(iter(sizes)) if sizes else (16, 9)
        meta = {
            "id": deck_id,
            "title": title,
            "subtitle": a.subtitle or "",
            "author": a.author or "",
            "date": date,
            "updated": a.updated or "",
            "description": a.description or "",
            "tags": [t.strip() for t in (a.tags or "").split(",") if t.strip()],
            "width": w,
            "height": h,
            "files": files,
            "notes": notes,
        }
        (dest / "deck.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        build_deck(dest)
        write_catalog()
        print(f"\nDone: decks/{deck_id}/  ({len(slides)} slides). Open index.html to check it, then commit.")
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


def make_thumbs(dest: Path) -> None:
    slides = sorted((dest / "slides").iterdir(), key=natural_key)
    if Image is None:
        warn("Pillow not installed (pip install pillow): no thumbnails, the grid will use full slides")
        return
    tdir = dest / "thumbs"
    tdir.mkdir(exist_ok=True)
    for i, p in enumerate(slides, 1):
        with Image.open(p) as im:
            im = im.convert("RGBA")
            bg = Image.new("RGB", im.size, "white")
            bg.paste(im, mask=im.split()[3])
            bg.thumbnail((THUMB_W, THUMB_W), Image.LANCZOS)
            bg.save(tdir / (p.stem + ".jpg"), "JPEG", quality=82, optimize=True)
        bar(i, len(slides), "thumbnails")


# ---------------------------------------------------------------- build
def file_entry(dest: Path, rel: str) -> dict | None:
    p = dest / rel
    if not p.exists():
        warn(f"{dest.name}: listed file missing: {rel}")
        return None
    return {"path": rel, "name": p.name, "bytes": p.stat().st_size}


def build_deck(dest: Path) -> dict:
    meta = json.loads((dest / "deck.json").read_text(encoding="utf-8"))
    meta["id"] = dest.name
    slides = sorted([p for p in (dest / "slides").iterdir() if p.suffix.lower() in IMG_EXT], key=natural_key)
    if not slides:
        die(f"{dest.name}: no slide images in slides/")
    if not (dest / "thumbs").is_dir() and Image is not None:
        make_thumbs(dest)
    notes = meta.get("notes") or []
    entries = []
    for i, p in enumerate(slides):
        t = dest / "thumbs" / (p.stem + ".jpg")
        entries.append({
            "src": f"slides/{p.name}",
            "thumb": f"thumbs/{t.name}" if t.exists() else f"slides/{p.name}",
            "notes": notes[i] if i < len(notes) else "",
        })
    files = {k: e for k, rel in (meta.get("files") or {}).items() if (e := file_entry(dest, rel))}
    deck = {k: meta.get(k, "") for k in ("id", "title", "subtitle", "author", "date", "updated", "description", "tags", "width", "height")}
    deck.update({"slides": entries, "files": files})

    (dest / "deck.js").write_text(
        "// Generated by tools/deck_tool.py from deck.json. Do not edit; edit deck.json and run: python tools/deck_tool.py build\n"
        "window.DECK = " + json.dumps(deck, indent=1, ensure_ascii=False) + ";\n", encoding="utf-8")
    page = TEMPLATE.read_text(encoding="utf-8")
    desc = deck["description"] or deck["subtitle"] or deck["title"]
    page = page.replace("{{TITLE}}", html.escape(deck["title"])).replace("{{DESCRIPTION}}", html.escape(desc))
    (dest / "index.html").write_text(page, encoding="utf-8")

    summary = {k: deck[k] for k in ("id", "title", "subtitle", "author", "date", "updated", "description", "tags")}
    summary.update({"slides": len(entries), "thumb": entries[0]["thumb"], "files": files})
    return summary


def write_catalog() -> list[dict]:
    decks = sorted([d for d in DECKS.iterdir() if (d / "deck.json").exists()]) if DECKS.exists() else []
    out = [build_deck(d) for d in decks]
    out.sort(key=lambda d: d.get("updated") or d.get("date") or "", reverse=True)
    (ROOT / "catalog.js").write_text(
        "// Generated by tools/deck_tool.py. Do not edit; run: python tools/deck_tool.py build\n"
        "window.CATALOG = " + json.dumps({"decks": out}, indent=1, ensure_ascii=False) + ";\n", encoding="utf-8")
    (ROOT / ".nojekyll").touch()
    return out


def cmd_build(_a) -> None:
    decks = [d for d in DECKS.iterdir() if (d / "deck.json").exists()] if DECKS.exists() else []
    step(1, 1, f"Rebuilding {len(decks)} deck(s) and catalog.js")
    out = write_catalog()
    for i, d in enumerate(out, 1):
        bar(i, len(out), d["id"])
    print("Done.")


def cmd_list(_a) -> None:
    decks = sorted(DECKS.glob("*/deck.json")) if DECKS.exists() else []
    if not decks:
        print("No decks yet.")
    for j in decks:
        d = json.loads(j.read_text(encoding="utf-8"))
        n = len([p for p in (j.parent / "slides").iterdir() if p.suffix.lower() in IMG_EXT])
        dl = ", ".join(d.get("files") or {}) or "none"
        print(f"{d.get('updated') or d.get('date')}  {j.parent.name}  ({n} slides; downloads: {dl})\n    {d.get('title')}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    ad = sub.add_parser("add", help="add a deck from a folder or .zip")
    ad.add_argument("source")
    ad.add_argument("--id", help="folder name under decks/ (default: <date>_<file-stem>)")
    ad.add_argument("--title")
    ad.add_argument("--subtitle")
    ad.add_argument("--author")
    ad.add_argument("--date", help="YYYY-MM-DD the deck was first given (default: today)")
    ad.add_argument("--updated", help="YYYY-MM-DD of the latest revision, if any")
    ad.add_argument("--description")
    ad.add_argument("--tags", help="comma separated")
    ad.add_argument("--force", action="store_true", help="replace an existing deck with the same id")
    ad.set_defaults(fn=cmd_add)
    sub.add_parser("build", help="regenerate deck pages and catalog.js").set_defaults(fn=cmd_build)
    sub.add_parser("list", help="list decks").set_defaults(fn=cmd_list)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
