# Presentations

Talks and group-meeting decks by Nathan Herling (UA ATLAS HEP Group). Every deck plays in the browser and can be downloaded as a **PDF**, a **PowerPoint (.pptx)** file, or a **single self-contained HTML** file.

It is a static site: plain HTML, CSS and JS, no build step to serve it, no framework. It runs on GitHub Pages and also straight from disk (double-click `index.html`).

## Decks

| Date | Deck | Slides |
|---|---|---|
| 30 Oct 2026, updated 3 Nov 2026 | [DisCo + the queen: closure gained, AUC paid](decks/2026-11-03_qn2-disco-vs-queen/) | 19 |

## Layout

```
index.html                 landing page: one card per deck (Present / PDF / PPTX / HTML)
catalog.js                 generated list of decks for the landing page
assets/
  site.css, site.js        landing page
  player.css, player.js    the slide player, shared by every deck
  templates/player.html    template for each deck's index.html
decks/<id>/
  deck.json                source of truth for the deck: title, dates, tags, files, speaker notes
  index.html, deck.js      generated from deck.json (do not edit by hand)
  slides/s-NN.png          slide images
  thumbs/s-NN.jpg          640 px thumbnails for the grid and the landing card
  downloads/               the .pdf, .pptx and single-file .html offered for download
tools/deck_tool.py         adds decks and rebuilds the generated files
```

## Player keys

| Key | Action |
|---|---|
| → Space PgDn / ← PgUp | next / previous slide (click the slide or swipe also moves on) |
| Home / End | first / last slide |
| G | overview grid |
| N | speaker notes (taken from the .pptx) |
| D | downloads menu |
| F | full screen (the bar hides when the mouse rests) |
| ? | key list |
| `#N` in the URL | open on slide N, e.g. `decks/<id>/#16` |

Ctrl+P prints one slide per page.

## Adding a deck

Point the tool at a folder or a .zip that holds the deck (a `slides/` folder of images, plus any of `.pdf`, `.pptx`, `*single_file*.html`):

```bash
pip install pillow python-pptx        # thumbnails and speaker notes (both optional)

python tools/deck_tool.py add path/to/deck.zip \
  --date 2026-10-30 --updated 2026-11-03 \
  --subtitle "..." --author "Nathan Herling" \
  --description "..." --tags "ATLAS,LLP"
```

The title comes from the HTML `<title>` (or the PPTX, or `--title`). The id defaults to `<updated or date>_<file-stem>`; set it with `--id`. If there is no image folder, the PDF pages are rendered instead (needs PyMuPDF or poppler's `pdftoppm`).

To change a deck later, edit its `deck.json` and run:

```bash
python tools/deck_tool.py build      # rewrites every deck's index.html + deck.js, and catalog.js
python tools/deck_tool.py list       # what is in the repo
```

Then add a row to the table above and commit. GitHub rejects files over 100 MB; the tool stops on those and warns above 50 MB.

## Publishing on GitHub Pages

Settings → Pages → Build and deployment → Source: **Deploy from a branch**, branch `main`, folder `/ (root)`. All links are relative, so the site works under `https://<user>.github.io/<repo>/`. The empty `.nojekyll` file tells Pages to serve the files as they are.
