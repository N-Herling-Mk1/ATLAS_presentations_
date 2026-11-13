#!/usr/bin/env python3
"""Add presentations to this repo, revise them, and rebuild the generated files.

  python tools/deck_tool.py add SOURCE [options]       # a new deck
  python tools/deck_tool.py update ID SOURCE [options] # a new revision of an existing deck (keeps its metadata)
  python tools/deck_tool.py build                      # rewrite every deck's index.html + deck.js, and catalog.js
  python tools/deck_tool.py list                       # show the decks in the repo
  python tools/deck_tool.py remote add REPO_FOLDER     # a card for a deck that lives in its own repo
  python tools/deck_tool.py remote refresh [ID ...]    # re-read those repos' clones after they change

SOURCE is a folder, a .zip, or a single one-file .html player. What is used from it:
  slides      a folder of slide images (slides/s-01.png ...); else the images embedded in the one-file HTML;
              else the PDF pages rendered (needs PyMuPDF or poppler's pdftoppm)
  *.pdf       the PDF download             } when missing, built from the slide images
  *.pptx      the PowerPoint download      }   (turn off with --no-generate)
              its speaker notes feed the player's notes panel
  *.html      the one-file HTML download (*single_file*.html inside a folder/zip, or SOURCE itself)
  README*.txt kept beside the deck as source_README.txt

Downloads are stored under fixed names <stem>.pdf / <stem>.pptx / <stem>_single_file.html, so links to a deck's
files survive revisions. `update` carries speaker notes over to the new slides by matching each new slide image to
the most similar old one (renumbering "Slide N of M."); slides with no match get empty notes and are listed.

Every deck lives in decks/<id>/ with deck.json as its hand-editable source of truth. After editing a
deck.json (title, tags, notes, ...) run `build`. Needs Python 3.8+; Pillow for thumbnails (optional),
python-pptx for speaker notes (optional).
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
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
        head = f.read(20000)                       # some exports put <title> late
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


# ---------------------------------------------------------------- reading a source
DATA_URI = re.compile(r"data:image/(png|jpe?g|webp);base64,([A-Za-z0-9+/=]+)")


def html_slides(page: Path, out: Path) -> list[Path]:
    """Pull the slide images out of a one-file HTML player (base64 data URIs, in order)."""
    import base64
    s = page.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"window\.SLIDES\s*=\s*\[(.*?)\]\s*;", s, re.S)    # the player's slide list, if present
    uris = DATA_URI.findall(m.group(1) if m else s)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, (ext, b64) in enumerate(uris, 1):
        p = out / f"s-{i:02d}.{'jpg' if ext.startswith('jp') else ext}"
        p.write_bytes(base64.b64decode(b64))
        paths.append(p)
        bar(i, len(uris), "slides extracted from the HTML")
    return paths


class Source:
    """Everything found in a SOURCE (folder, .zip or one-file .html)."""

    def __init__(self, path: str):
        self.path = Path(path).expanduser().resolve()
        self.tmp: list[Path] = []
        if not self.path.exists():
            die(f"not found: {self.path}")
        if self.path.is_file() and self.path.suffix.lower() == ".zip":
            root = self._tmpdir("deck_")
            safe_extract(self.path, root)
            info(f"unzipped to {root}")
        elif self.path.is_file() and self.path.suffix.lower() in (".html", ".htm"):
            root = None
        elif self.path.is_dir():
            root = self.path
        else:
            die("SOURCE must be a folder, a .zip, or a one-file .html player")

        if root is None:
            self.root = self.path.parent
            self.pdf = self.pptx = self.readme = self.slide_dir = None
            self.html = self.path
        else:
            self.root = root
            self.pdf = first(root, "*.pdf")
            self.pptx = first(root, "*.pptx")
            self.html = first(root, "*single_file*.html") or first(root, "*single*.html")
            self.readme = first(root, "README*.txt") or first(root, "README*.md")
            self.slide_dir = find_slide_dir(root)
        for label, p in (("slides", self.slide_dir), ("pdf", self.pdf), ("pptx", self.pptx), ("html", self.html), ("readme", self.readme)):
            info(f"{label:7s}: {p.name if p and label != 'slides' else (p.relative_to(self.root) if p else '-')}")

    def _tmpdir(self, prefix: str) -> Path:
        d = Path(tempfile.mkdtemp(prefix=prefix))
        self.tmp.append(d)
        return d

    def slides(self) -> list[Path]:
        """Slide images, in order: an image folder first, else the one-file HTML, else the PDF rendered."""
        if self.slide_dir:
            return sorted([p for p in self.slide_dir.iterdir() if p.is_file() and p.suffix.lower() in IMG_EXT], key=natural_key)
        if self.html:
            got = html_slides(self.html, self._tmpdir("htmlslides_"))
            if got:
                return got
            warn("no embedded slide images in the HTML")
        if self.pdf:
            info("no image folder: rendering the PDF")
            return render_pdf(self.pdf, self._tmpdir("pdfpages_"))
        die("no slide images, no one-file HTML with slides, and no PDF to render")
        return []

    def title(self) -> str | None:
        for cand in [self.html, self.slide_dir and self.slide_dir.parent / "index.html"]:
            if cand and cand.exists():
                t = html_title(cand)
                if t:
                    return t
        return pptx_title(self.pptx) if self.pptx else None

    def cleanup(self) -> None:
        for d in self.tmp:
            shutil.rmtree(d, ignore_errors=True)


# ---------------------------------------------------------------- generating PDF / PPTX from slide images
def make_pdf(slides: list[Path], out: Path) -> bool:
    if Image is None:
        warn("Pillow not installed: cannot build the PDF")
        return False
    pages = []
    for i, p in enumerate(slides, 1):
        with Image.open(p) as im:
            pages.append(im.convert("RGB"))
        bar(i, len(slides), "PDF pages")
    w = pages[0].size[0]
    pages[0].save(out, "PDF", save_all=True, append_images=pages[1:], resolution=w / 13.333)   # 13.333 in wide, like PowerPoint 16:9
    return True


def make_pptx(slides: list[Path], notes: list[str], out: Path) -> bool:
    try:
        from pptx import Presentation
        from pptx.util import Emu
    except ImportError:
        warn("python-pptx not installed: cannot build the PPTX")
        return False
    size = image_size(slides[0]) or (16, 9)
    pres = Presentation()
    pres.slide_width = Emu(12192000)
    pres.slide_height = Emu(round(12192000 * size[1] / size[0]))
    blank = pres.slide_layouts[6]
    for i, p in enumerate(slides):
        s = pres.slides.add_slide(blank)
        s.shapes.add_picture(str(p), 0, 0, width=pres.slide_width, height=pres.slide_height)
        if i < len(notes) and notes[i]:
            s.notes_slide.notes_text_frame.text = notes[i]
        bar(i + 1, len(slides), "PPTX slides")
    pres.save(str(out))
    return True


# ---------------------------------------------------------------- carrying notes across a revision
# Slide difference = mean grey-level difference (0-255) between 64x36 copies. On the QN2 revision: unchanged slides
# 0.1-0.9, slides with a label added 2.0-4.1, different slides 5.2 and up. That margin alone is too thin for
# text-on-white slides, so matches are also forced to keep the slide order (a diff-style alignment, below).
SAME, EDITED, GAP = 1.2, 7.0, 6.0


def _sig(p: Path):
    with Image.open(p) as im:
        return im.convert("L").resize((64, 36), Image.BILINEAR).tobytes()


def match_slides(new: list[Path], old: list[Path]) -> list[tuple[int | None, float]]:
    """Align new slides to old ones, keeping order (like diff): each new slide gets (old index, difference) or
    (None, smallest difference to any old slide) when it is a slide the old deck did not have."""
    O = [_sig(p) for p in old]
    C = []
    for i, p in enumerate(new, 1):
        a = _sig(p)
        C.append([sum(abs(x - y) for x, y in zip(a, b)) / len(a) for b in O])
        bar(i, len(new), "slides compared")
    n, m = len(new), len(old)
    INF = float("inf")
    D = [[INF] * (m + 1) for _ in range(n + 1)]       # D[i][j]: best cost aligning new[:i] with old[:j]
    D[0] = [j * GAP for j in range(m + 1)]
    for i in range(1, n + 1):
        D[i][0] = i * GAP
        for j in range(1, m + 1):
            c = C[i - 1][j - 1]
            D[i][j] = min(D[i - 1][j] + GAP,                                   # new slide i inserted
                          D[i][j - 1] + GAP,                                   # old slide j dropped
                          D[i - 1][j - 1] + c if c <= EDITED else INF)         # same slide, maybe edited
    out: list[tuple[int | None, float]] = [(None, 0.0)] * n
    i, j = n, m
    while i > 0:
        c = C[i - 1][j - 1] if j > 0 else INF
        if j > 0 and c <= EDITED and D[i][j] == D[i - 1][j - 1] + c:
            out[i - 1] = (j - 1, c); i -= 1; j -= 1
        elif D[i][j] == D[i - 1][j] + GAP:
            out[i - 1] = (None, min(C[i - 1]) if m else 0.0); i -= 1
        else:
            j -= 1
    return out


def renumber(note: str, i: int, n: int) -> str:
    return re.sub(r"^Slide \d+ of \d+\.", f"Slide {i} of {n}.", note)


# ---------------------------------------------------------------- installing slides + downloads into a deck folder
def install_slides(dest: Path, imgs: list[Path]) -> tuple[list[Path], tuple[int, int]]:
    if (dest / "slides").exists():
        shutil.rmtree(dest / "slides")
    if (dest / "thumbs").exists():
        shutil.rmtree(dest / "thumbs")
    (dest / "slides").mkdir(parents=True)
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
    w, h = min(sizes) if sizes else (16, 9)
    return slides, (w, h)


def install_downloads(dest: Path, src: Source, stem: str, slides: list[Path], notes: list[str], generate: bool) -> dict:
    """Copy the source's PDF / PPTX / HTML under fixed names <stem>.pdf, <stem>.pptx, <stem>_single_file.html.
    Missing PDF/PPTX are built from the slide images when `generate` is on. Returns deck.json's `files`."""
    dl = dest / "downloads"
    if dl.exists():
        shutil.rmtree(dl)
    dl.mkdir()
    files, made = {}, []
    names = {"pdf": f"{stem}.pdf", "pptx": f"{stem}.pptx", "html": f"{stem}_single_file.html"}
    for kind, p in (("pdf", src.pdf), ("pptx", src.pptx), ("html", src.html)):
        if p:
            check_size(p)
            shutil.copyfile(p, dl / names[kind])                 # copyfile: do not carry read-only bits over
            files[kind] = f"downloads/{names[kind]}"
            info(f"{kind:5s} {names[kind]}  ({mb(p.stat().st_size)}, from the source)")
    if generate and "pdf" not in files and make_pdf(slides, dl / names["pdf"]):
        files["pdf"] = f"downloads/{names['pdf']}"
        made.append("pdf")
    if generate and "pptx" not in files and make_pptx(slides, notes, dl / names["pptx"]):
        files["pptx"] = f"downloads/{names['pptx']}"
        made.append("pptx")
    for kind in made:
        p = dl / names[kind]
        check_size(p)
        info(f"{kind:5s} {names[kind]}  ({mb(p.stat().st_size)}, built from the slide images)")
    if "html" not in files:
        info("html  none in the source: no one-file HTML download for this deck")
    return files


def write_meta(dest: Path, meta: dict, name: str = "deck.json") -> None:
    (dest / name).write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- add
def cmd_add(a: argparse.Namespace) -> None:
    S = 6
    step(1, S, f"Reading {Path(a.source).name}")
    src = Source(a.source)
    try:
        step(2, S, "Choosing id and title")
        title = a.title or src.title()
        stem = a.name or (src.pdf or src.pptx or src.html or src.path).stem.replace("_single_file", "")
        title = title or stem
        date = a.date or dt.date.today().isoformat()
        deck_id = a.id or f"{a.updated or date}_{slugify(stem)}"
        dest = DECKS / deck_id
        if dest.exists():
            if not a.force:
                die(f"decks/{deck_id} already exists: use `update {deck_id} SOURCE` for a new revision, "
                    f"--force to start it over, or --id for a new deck")
            shutil.rmtree(dest)
        info(f"id     : {deck_id}")
        info(f"title  : {title}")

        step(3, S, "Copying slide images")
        slides, (w, h) = install_slides(dest, src.slides())

        step(4, S, "Making thumbnails")
        make_thumbs(dest)

        step(5, S, "Reading speaker notes; downloads")
        notes = pptx_notes(src.pptx) if src.pptx else []
        if notes:
            info(f"notes on {sum(1 for n in notes if n)} of {len(notes)} slides")
            if len(notes) != len(slides):
                warn(f"PPTX has {len(notes)} slides but there are {len(slides)} images; notes are matched by position")
        files = install_downloads(dest, src, stem, slides, notes, not a.no_generate)
        if src.readme:
            shutil.copy2(src.readme, dest / ("source_README" + src.readme.suffix))

        step(6, S, "Writing deck.json, index.html, deck.js, catalog.js")
        write_meta(dest, {
            "id": deck_id, "title": title, "subtitle": a.subtitle or "", "author": a.author or "",
            "date": date, "updated": a.updated or "", "description": a.description or "",
            "tags": [t.strip() for t in (a.tags or "").split(",") if t.strip()],
            "width": w, "height": h, "files": files, "notes": notes,
        })
        write_catalog()
        print(f"\nDone: decks/{deck_id}/  ({len(slides)} slides). Open index.html to check it, then commit.")
    finally:
        src.cleanup()


# ---------------------------------------------------------------- update
def cmd_update(a: argparse.Namespace) -> None:
    S = 7
    dest = DECKS / a.id
    if not (dest / "deck.json").exists():
        die(f"no deck decks/{a.id}/ (see `list`); use `add` for a new deck")
    meta = json.loads((dest / "deck.json").read_text(encoding="utf-8"))

    step(1, S, f"Reading {Path(a.source).name}")
    src = Source(a.source)
    keep = Path(tempfile.mkdtemp(prefix="oldslides_"))
    try:
        step(2, S, "Collecting the new slides")
        new = src.slides()
        old = sorted([p for p in (dest / "slides").iterdir() if p.suffix.lower() in IMG_EXT], key=natural_key)
        old = [Path(shutil.copy2(p, keep / p.name)) for p in old]
        old_notes = meta.get("notes") or []
        info(f"{len(old)} slides now -> {len(new)} slides in the revision")

        step(3, S, "Matching new slides to old ones")
        notes: list[str]
        if src.pptx:
            notes = pptx_notes(src.pptx)
            info("notes taken from the revision's PPTX")
            match = None
        elif Image is None:
            warn("Pillow not installed: cannot match slides, so no notes are carried over")
            match, notes = None, [""] * len(new)
        else:
            match = match_slides(new, old)
            notes = []
            print("      new  <- old   diff  status            size")
            for i, (k, d) in enumerate(match, 1):
                ns = image_size(new[i - 1])
                if k is None:
                    status, note = "NEW (no notes)", ""
                else:
                    status = "same" if d <= SAME else "edited"
                    note = renumber(old_notes[k], i, len(new)) if k < len(old_notes) else ""
                    os_ = image_size(old[k])
                    if ns and os_ and ns[0] < os_[0]:
                        status += f", lower res than before ({os_[0]}x{os_[1]})"
                notes.append(note)
                print(f"      {i:3d}  <- {('-' if k is None else k + 1):>3}  {d:5.1f}  {status:16s}  {ns[0]}x{ns[1]}" if ns else "")
            dropped = sorted(set(range(len(old))) - {k for k, _ in match if k is not None})
            if dropped:
                info(f"old slides with no match in the revision (dropped or rewritten): {', '.join(str(k + 1) for k in dropped)}")

        step(4, S, "Replacing slide images")
        slides, (w, h) = install_slides(dest, new)

        step(5, S, "Making thumbnails")
        make_thumbs(dest)

        step(6, S, "Downloads")
        old_files = meta.get("files") or {}
        stem = a.name or next((Path(v).stem.replace("_single_file", "") for v in old_files.values()), slugify(a.id))
        files = install_downloads(dest, src, stem, slides, notes, not a.no_generate)

        step(7, S, "Writing deck.json, index.html, deck.js, catalog.js")
        for k in ("title", "subtitle", "author", "date", "description"):
            if getattr(a, k):
                meta[k] = getattr(a, k)
        if a.tags:
            meta["tags"] = [t.strip() for t in a.tags.split(",") if t.strip()]
        meta["updated"] = a.updated or meta.get("updated") or dt.date.today().isoformat()
        meta.update({"width": w, "height": h, "files": files, "notes": notes})
        write_meta(dest, meta)
        write_catalog()
        print(f"\nDone: decks/{a.id}/ now has {len(slides)} slides. Check the notes in deck.json for the slides marked NEW, then commit.")
    finally:
        src.cleanup()
        shutil.rmtree(keep, ignore_errors=True)


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


# ---------------------------------------------------------------- decks that live in their own repos
# A deck can also live in its own GitHub repo (e.g. ATLAS_presentations_TRUSS) with its own player on its own
# GitHub Pages site. `remote add` reads a local clone of that repo once and records what the landing card needs in
# remotes/<id>/remote.json (+ a first-slide thumbnail). The card's Present / PDF / PPTX / HTML buttons point at the
# other repo's Pages site, so the files themselves are never copied here. `remote refresh` re-reads the clones after
# those repos change. `build` never needs the clones.
REMOTES = ROOT / "remotes"
DL_KIND = {".pdf": "pdf", ".pptx": "pptx", ".html": "html", ".htm": "html"}
HAND_KEYS = ("title", "subtitle", "author", "date", "updated", "description", "tags")


def git_out(repo: Path, *args: str) -> str:
    try:
        r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=30)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def github_slug(url: str) -> tuple[str, str] | None:
    m = re.search(r"github\.com[:/]([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", url or "")
    return (m.group(1), m.group(2)) if m else None


def pdf_pages(pdf: Path) -> int | None:
    try:
        import fitz
        with fitz.open(pdf) as doc:
            return doc.page_count
    except ImportError:
        pass
    if shutil.which("pdfinfo"):
        m = re.search(r"^Pages:\s+(\d+)", subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True).stdout, re.M)
        if m:
            return int(m.group(1))
    n = len(re.findall(rb"/Type\s*/Page(?![s\w])", pdf.read_bytes()))   # crude, but right for simple PDFs
    return n or None


def pdf_first_page(pdf: Path, out_dir: Path) -> Path | None:
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        import fitz
        with fitz.open(pdf) as doc:
            page = doc[0]
            zoom = 2 * THUMB_W / max(page.rect.width, 1)
            p = out_dir / "p1.png"
            page.get_pixmap(matrix=fitz.Matrix(zoom, zoom)).save(p)
            return p
    except ImportError:
        pass
    if shutil.which("pdftoppm"):
        subprocess.run(["pdftoppm", "-f", "1", "-l", "1", "-singlefile", "-scale-to-x", str(2 * THUMB_W),
                        "-scale-to-y", "-1", "-png", str(pdf), str(out_dir / "p1")], check=True)
        return out_dir / "p1.png"
    return None


def meta_description(p: Path) -> str:
    with open(p, "r", encoding="utf-8", errors="ignore") as f:
        head = f.read(20000)
    m = re.search(r"<meta\s+name=['\"]description['\"]\s+content=(['\"])(.*?)\1", head, re.S | re.I)
    return html.unescape(m.group(2).strip()) if m else ""


def readme_bits(clone: Path) -> tuple[str, str]:
    """(H1, first line of the first paragraph after it) from README.md, markdown stripped."""
    rd = next((p for p in (clone / "README.md", clone / "readme.md") if p.exists()), None)
    if not rd:
        return "", ""
    plain = lambda s: re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s).replace("**", "").replace("`", "").strip()
    h1, para = "", ""
    for line in rd.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = line.strip()
        if not h1:
            if s.startswith("# "):
                h1 = plain(s[2:])
            continue
        if not s or s.startswith(("<", "#", "|", ">", "!", "-", "*  ", "```")):
            if para:
                break
            continue
        para = plain(s)
        break
    return h1, para


def scan_remote(clone: Path, work: Path) -> tuple[dict, Path | None]:
    """Read a deck repo's clone: title, blurb, dates, slide count, downloads, and an image for the thumbnail."""
    page = clone / "index.html"
    if not page.exists():
        die(f"{clone}: no index.html at the top of the repo, so there is no player to link to")
    h1, blurb = readme_bits(clone)
    title = html_title(page) or h1 or clone.name
    files: dict = {}
    dl = clone / "downloads"
    for p in sorted(dl.iterdir(), key=natural_key) if dl.is_dir() else []:
        k = DL_KIND.get(p.suffix.lower())
        if not k or not p.is_file():
            continue
        if k in files and not (k == "html" and "single_file" in p.name):   # prefer the *single_file*.html
            continue
        files[k] = {"path": f"downloads/{p.name}", "name": p.name, "bytes": p.stat().st_size}
    slide_imgs = sorted([p for p in (clone / "slides").iterdir() if p.suffix.lower() in IMG_EXT],
                        key=natural_key) if (clone / "slides").is_dir() else []
    pdf = dl / files["pdf"]["name"] if "pdf" in files else None
    slides = (pdf_pages(pdf) if pdf else None) or len(slide_imgs) or None
    image = None
    if pdf:
        try:
            image = pdf_first_page(pdf, work)
        except (subprocess.SubprocessError, RuntimeError, OSError) as e:
            warn(f"could not render page 1 of {pdf.name}: {e}")
    if image is None and slide_imgs:
        image = slide_imgs[0]
    if image is None:
        image = next((clone / c for c in ("assets/logo.webp", "assets/logo.png", "logo.png", "favicon.png",
                                          "assets/favicon.png") if (clone / c).exists()), None)
    first_c = git_out(clone, "log", "--reverse", "--format=%cs").splitlines()
    last_c = git_out(clone, "log", "-1", "--format=%cs")
    scan = {
        "title": title,
        "subtitle": h1 if h1 and h1 != title else "",
        "description": meta_description(page) or blurb,
        "date": first_c[0] if first_c else dt.date.today().isoformat(),
        "updated": last_c,
        "slides": slides,
        "files": files,
        "commit": git_out(clone, "rev-parse", "--short", "HEAD"),
        "scanned": dt.date.today().isoformat(),
    }
    if scan["updated"] == scan["date"]:
        scan["updated"] = ""
    return scan, image


def save_remote_thumb(dest: Path, image: Path | None) -> str:
    for old in dest.glob("thumb.*"):
        old.unlink()
    if image is None:
        warn("no PDF, slide image or logo found: the card will have no picture")
        return ""
    if Image is None:
        warn("Pillow not installed (pip install pillow): using the image at full size as the thumbnail")
        shutil.copy2(image, dest / ("thumb" + image.suffix.lower()))
        return "thumb" + image.suffix.lower()
    with Image.open(image) as im:
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, "white")
        bg.paste(im, mask=im.split()[3])
        bg.thumbnail((THUMB_W, THUMB_W), Image.LANCZOS)
        bg.save(dest / "thumb.jpg", "JPEG", quality=82, optimize=True)
    return "thumb.jpg"


def remote_clone(meta: dict) -> Path:
    """Where the clone is: remote.json's "clone" (relative to this repo), else a sibling folder named like the repo."""
    if meta.get("clone"):
        return (ROOT / meta["clone"]).resolve()
    slug = github_slug(meta.get("repo", ""))
    return (ROOT.parent / slug[1]).resolve() if slug else ROOT.parent / "?"


def remote_summary(dest: Path) -> dict:
    meta = json.loads((dest / "remote.json").read_text(encoding="utf-8"))
    scan = meta.get("scan") or {}
    pages = meta["pages"].rstrip("/") + "/"
    d = {k: (meta.get(k) or scan.get(k) or ([] if k == "tags" else "")) for k in HAND_KEYS}
    thumb = next((p.name for p in sorted(dest.glob("thumb.*"))), "")
    d.update({
        "id": dest.name,
        "slides": scan.get("slides") or 0,
        "thumb": f"remotes/{dest.name}/{thumb}" if thumb else "",
        "url": pages,
        "repo": meta.get("repo", ""),
        "files": {k: {"path": pages + f["path"], "name": f["name"], "bytes": f["bytes"]}
                  for k, f in (scan.get("files") or {}).items()},
    })
    return d


def cmd_remote_add(a: argparse.Namespace) -> None:
    S = 4
    step(1, S, f"Finding the clone of {a.source}")
    p = Path(a.source)
    clone = (p if p.is_dir() else ROOT.parent / a.source).resolve()
    if not clone.is_dir():
        die(f"no folder {a.source} (looked in {ROOT.parent}); clone the repo next to this one or give its path")
    if clone == ROOT.resolve():
        die("that is this repo; use `add` for decks stored here")
    origin = git_out(clone, "remote", "get-url", "origin")
    slug = github_slug(a.repo or origin)
    if not slug:
        die(f"{clone.name}: origin is not a GitHub URL ({origin or 'none'}); pass --repo https://github.com/<owner>/<repo>")
    owner, repo = slug
    pages = a.pages or f"https://{owner.lower()}.github.io/{repo}/"
    info(f"clone  : {clone}")
    info(f"repo   : https://github.com/{owner}/{repo}")
    info(f"pages  : {pages}")

    step(2, S, "Reading title, downloads, slide count and dates")
    with tempfile.TemporaryDirectory() as tmp:
        scan, image = scan_remote(clone, Path(tmp))
        stem = re.sub(r"^atlas_presentations_", "", repo, flags=re.I)
        deck_id = a.id or f"{a.date or scan['date']}_{slugify(stem)}"
        dest = REMOTES / deck_id
        if dest.exists() and not a.force:
            die(f"remotes/{deck_id} already exists: use `remote refresh {deck_id}`, or --force to start it over")
        if (DECKS / deck_id).exists():
            die(f"decks/{deck_id} already exists here; pick another --id")
        shutil.rmtree(dest, ignore_errors=True)
        dest.mkdir(parents=True)
        info(f"id     : {deck_id}")
        info(f"title  : {a.title or scan['title']}")
        info(f"slides : {scan['slides'] or '?'}   downloads: {', '.join(scan['files']) or 'none'}")

        step(3, S, "Making the thumbnail")
        save_remote_thumb(dest, image)

    step(4, S, "Writing remote.json and catalog.js")
    meta = {
        "repo": f"https://github.com/{owner}/{repo}", "pages": pages,
        "title": a.title or "", "subtitle": a.subtitle or "", "author": a.author or "Nathan Herling",
        "date": a.date or "", "updated": a.updated or "", "description": a.description or "",
        "tags": [t.strip() for t in (a.tags or "").split(",") if t.strip()] or ["ATLAS", stem],
        "scan": scan,
    }
    if p.is_dir() and clone != (ROOT.parent / repo).resolve():
        meta["clone"] = os.path.relpath(clone, ROOT)
    write_meta(dest, meta, "remote.json")
    write_catalog()
    print(f"\nDone: remotes/{deck_id}/. Open index.html to check the card, then commit remotes/ and catalog.js.")


def cmd_remote_refresh(a: argparse.Namespace) -> None:
    dirs = sorted(d for d in REMOTES.iterdir() if (d / "remote.json").exists()) if REMOTES.exists() else []
    if a.ids:
        missing = set(a.ids) - {d.name for d in dirs}
        if missing:
            die(f"no such remote deck(s): {', '.join(sorted(missing))}")
        dirs = [d for d in dirs if d.name in a.ids]
    if not dirs:
        die("no remote decks yet; add one with: remote add <repo-folder>")
    step(1, 2, f"Re-reading {len(dirs)} clone(s)")
    for i, dest in enumerate(dirs, 1):
        meta = json.loads((dest / "remote.json").read_text(encoding="utf-8"))
        clone = remote_clone(meta)
        if not clone.is_dir():
            warn(f"{dest.name}: clone not found at {clone}; kept the old record (git clone it there, or set \"clone\")")
            continue
        if git_out(clone, "status", "--porcelain"):
            warn(f"{dest.name}: {clone.name} has uncommitted changes; the card describes the working copy, not what is on GitHub")
        old = meta.get("scan") or {}
        with tempfile.TemporaryDirectory() as tmp:
            meta["scan"], image = scan_remote(clone, Path(tmp))
            save_remote_thumb(dest, image)
        write_meta(dest, meta, "remote.json")
        changed = [k for k in ("title", "slides", "files", "updated", "commit") if old.get(k) != meta["scan"].get(k)]
        bar(i, len(dirs), f"{dest.name}: " + (", ".join(changed) + " changed" if changed else "no change"))
    step(2, 2, "Writing catalog.js")
    write_catalog()
    print("Done. Commit remotes/ and catalog.js.")


def cmd_remote_remove(a: argparse.Namespace) -> None:
    dest = REMOTES / a.id
    if not (dest / "remote.json").exists():
        die(f"no such remote deck: {a.id}")
    shutil.rmtree(dest)
    write_catalog()
    print(f"Removed remotes/{a.id}/ from the landing page (the other repo is untouched).")


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
    remotes = sorted(d for d in REMOTES.iterdir() if (d / "remote.json").exists()) if REMOTES.exists() else []
    out += [remote_summary(d) for d in remotes]
    out.sort(key=lambda d: d.get("updated") or d.get("date") or "", reverse=True)
    (ROOT / "catalog.js").write_text(
        "// Generated by tools/deck_tool.py. Do not edit; run: python tools/deck_tool.py build\n"
        "window.CATALOG = " + json.dumps({"decks": out}, indent=1, ensure_ascii=False) + ";\n", encoding="utf-8")
    (ROOT / ".nojekyll").touch()
    return out


def cmd_build(_a) -> None:
    decks = [d for d in DECKS.iterdir() if (d / "deck.json").exists()] if DECKS.exists() else []
    nr = len(list(REMOTES.glob("*/remote.json"))) if REMOTES.exists() else 0
    step(1, 1, f"Rebuilding {len(decks)} deck(s) and catalog.js" + (f" (+ {nr} from other repos, as last read)" if nr else ""))
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
    for j in sorted(REMOTES.glob("*/remote.json")) if REMOTES.exists() else []:
        d = remote_summary(j.parent)
        sc = json.loads(j.read_text(encoding="utf-8")).get("scan") or {}
        print(f"{d['updated'] or d['date']}  {d['id']}  [other repo: {d['repo']}]  ({d['slides']} slides; "
              f"downloads: {', '.join(d['files']) or 'none'}; read {sc.get('scanned', '?')} at {sc.get('commit') or '?'})\n    {d['title']}")


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
    ad.add_argument("--name", help="file stem for the downloads (default: the source's PDF/PPTX/HTML name)")
    ad.add_argument("--no-generate", action="store_true", help="do not build a missing PDF/PPTX from the slides")
    ad.add_argument("--force", action="store_true", help="replace an existing deck with the same id")
    ad.set_defaults(fn=cmd_add)
    up = sub.add_parser("update", help="replace a deck's slides and downloads with a new revision")
    up.add_argument("id", help="the deck's folder name under decks/")
    up.add_argument("source")
    for f in ("--title", "--subtitle", "--author", "--date", "--description"):
        up.add_argument(f)
    up.add_argument("--updated", help="YYYY-MM-DD of this revision (default: keep the current value, else today)")
    up.add_argument("--tags", help="comma separated; replaces the current tags")
    up.add_argument("--name", help="file stem for the downloads (default: keep the current names)")
    up.add_argument("--no-generate", action="store_true", help="do not build a missing PDF/PPTX from the slides")
    up.set_defaults(fn=cmd_update)
    sub.add_parser("build", help="regenerate deck pages and catalog.js").set_defaults(fn=cmd_build)
    sub.add_parser("list", help="list decks").set_defaults(fn=cmd_list)
    rm = sub.add_parser("remote", help="decks that live in their own repos (cards here, files there)")
    rsub = rm.add_subparsers(dest="rcmd", required=True)
    ra = rsub.add_parser("add", help="add a card for a deck repo, read from its local clone")
    ra.add_argument("source", help="the clone's folder, or just its name if it sits next to this repo")
    ra.add_argument("--id", help="folder name under remotes/ (default: <first-commit date>_<repo suffix>)")
    ra.add_argument("--repo", help="https://github.com/<owner>/<repo> (default: the clone's origin)")
    ra.add_argument("--pages", help="its GitHub Pages URL (default: https://<owner>.github.io/<repo>/)")
    for f in ("--title", "--subtitle", "--author", "--description"):
        ra.add_argument(f, help="(default: read from the repo)" if f != "--author" else "(default: Nathan Herling)")
    ra.add_argument("--date", help="YYYY-MM-DD (default: the repo's first commit)")
    ra.add_argument("--updated", help="YYYY-MM-DD (default: the repo's last commit)")
    ra.add_argument("--tags", help="comma separated")
    ra.add_argument("--force", action="store_true", help="replace an existing card with the same id")
    ra.set_defaults(fn=cmd_remote_add)
    rr = rsub.add_parser("refresh", help="re-read the clones (after those repos change) and rebuild catalog.js")
    rr.add_argument("ids", nargs="*", help="which remote decks (default: all)")
    rr.set_defaults(fn=cmd_remote_refresh)
    rx = rsub.add_parser("remove", help="drop a remote deck's card")
    rx.add_argument("id")
    rx.set_defaults(fn=cmd_remote_remove)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
