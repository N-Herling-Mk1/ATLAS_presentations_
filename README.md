<img src="assets/icon/icon.svg" width="96" alt="">

# Presentations

Talks and group-meeting decks by Nathan Herling (UA ATLAS HEP Group). Every deck plays in the browser and can be downloaded as a **PDF**, a **PowerPoint (.pptx)** file, or a **single self-contained HTML** file.

It is a static site: plain HTML, CSS and JS, no build step to serve it, no framework. It runs on GitHub Pages and also straight from disk (double-click `index.html`).

## Decks

| Date | Deck | Slides |
|---|---|---|
| 13 Nov 2026 | [DisCo + the queen, endcap and barrel: closure gained, and how far it holds](https://n-herling-mk1.github.io/ATLAS_presentations_DNCn_QN/) (own repo: [ATLAS_presentations_DNCn_QN](https://github.com/N-Herling-Mk1/ATLAS_presentations_DNCn_QN)) | 22 |
| 13 Nov 2026 | [TRUSS: what 376 training runs taught us](https://n-herling-mk1.github.io/ATLAS_presentations_TRUSS/) (own repo: [ATLAS_presentations_TRUSS](https://github.com/N-Herling-Mk1/ATLAS_presentations_TRUSS)) | 19 |
| 13 Nov 2026 | [UNKNOT mk1: bottom line](https://n-herling-mk1.github.io/ATLAS_presentations_unKNOT/) (own repo: [ATLAS_presentations_unKNOT](https://github.com/N-Herling-Mk1/ATLAS_presentations_unKNOT)) | 23 |
| 6 Nov 2026 | [STAVE: pretrain the barrel across regions](decks/2026-11-06_stave-pretraining-across-regions/) | 8 |
| 5 Nov 2026 | [LEXICON mk_1: does a detector event have a grammar?](decks/2026-11-05_lexicon-mk1/) | 49 |
| 30 Oct 2026, updated 3 Nov 2026 | [DisCo + the queen: closure gained, AUC paid](decks/2026-11-03_qn2-disco-vs-queen/) | 20 |
| 15 Oct 2026 | [BEAM (agent): PIPE and HALO, idea and plan](decks/2026-10-15_beam-agent-idea-and-plan/) | 18 |
| 14 Oct 2026 | [STAVE: Ideas to run on the barrel](decks/2026-10-14_stave-barrel-ideas/) | 18 |
| 7 Oct 2026, updated 14 Oct 2026 | [Information theory for ATLAS data](decks/2026-10-07_information-theory-atlas-v0/) | 7 |

## Layout

```
index.html                 landing page: one card per deck (Present / PDF / PPTX / HTML)
catalog.js                 generated list of decks for the landing page
assets/
  site.css, site.js        landing page
  icon/                    repo icon: icon.svg (square), icon-wide.svg, PNGs at 512 and 32 px, social-preview-1200x800.png
  player.css, player.js    the slide player, shared by every deck
  templates/player.html    template for each deck's index.html
decks/<id>/
  deck.json                source of truth for the deck: title, dates, tags, files, speaker notes
  index.html, deck.js      generated from deck.json (do not edit by hand)
  slides/s-NN.png          slide images
  thumbs/s-NN.jpg          640 px thumbnails for the grid and the landing card
  downloads/               the .pdf, .pptx and single-file .html offered for download
remotes/<id>/              decks that live in their own repos (see below)
  remote.json              repo + Pages URL, overrides you set, and what was last read from the clone
  thumb.jpg                first page of that repo's PDF, 640 px
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

### A new revision of an existing deck

Do not drop a new file into `downloads/`: the player, thumbnails, PDF, PPTX and notes would still be the old version. Run:

```bash
python tools/deck_tool.py update 2026-11-03_qn2-disco-vs-queen path/to/new_deck.html   # or a folder / .zip
```

SOURCE can be the one-file HTML player alone: the slides are taken out of it. `update` keeps the deck's title, tags and dates (override any with the same flags as `add`), keeps the download file names, builds a PDF and an image-per-slide PPTX when the source has none, and carries the speaker notes over by matching each new slide to the old one it came from (diff-style, in order). It prints the match table; slides marked NEW get empty notes, to fill in `deck.json`, then `build`.

### Editing a deck

To change a deck later, edit its `deck.json` and run:

```bash
python tools/deck_tool.py build      # rewrites every deck's index.html + deck.js, and catalog.js
python tools/deck_tool.py list       # what is in the repo
```

Then add a row to the table above and commit. GitHub rejects files over 100 MB; the tool stops on those and warns above 50 MB.

## Decks in their own repos

Some decks live in their own repo with their own player (`ATLAS_presentations_TRUSS`, `_unKNOT`, `_DNCn_QN`). They still get a card here: **Present** opens that repo's GitHub Pages site and the download buttons fetch from it, so nothing is copied into this repo except a small `remote.json` and a thumbnail. The card shows a link to the other repo.

Clone the deck repo next to this one, then:

```bash
pip install pillow pymupdf          # thumbnail from the PDF's first page (or poppler's pdftoppm instead of pymupdf)

python tools/deck_tool.py remote add ATLAS_presentations_TRUSS --tags "ATLAS,LLP,TRUSS"
python tools/deck_tool.py remote refresh            # after any of those repos change: re-reads every clone
python tools/deck_tool.py remote refresh 2026-11-13_truss
python tools/deck_tool.py remote remove 2026-11-13_truss
```

What is read from the clone: the title from `index.html`'s `<title>`, the description from its `<meta name="description">` (else the README's first paragraph), the subtitle from the README's heading when it differs from the title, the downloads from `downloads/*.pdf|pptx|html`, the slide count from the PDF's pages, and the dates from the first and last commits. Any of these can be pinned with `--title`, `--date`, etc., or by editing the top-level fields in `remote.json`; a non-empty field there always wins over what was read. `refresh` only rewrites the `scan` block and the thumbnail.

`build` does not need the clones: it uses what `remote.json` recorded. So the card only changes when you run `remote refresh` and commit; the download links always point at the live files in the other repo. Each deck repo needs GitHub Pages on (branch `main`, folder `/`), or Present and the downloads give 404.

## Publishing on GitHub Pages

Settings → Pages → Build and deployment → Source: **Deploy from a branch**, branch `main`, folder `/ (root)`. All links are relative, so the site works under `https://<user>.github.io/<repo>/`. The empty `.nojekyll` file tells Pages to serve the files as they are.

## Icon

`assets/icon/` holds the repo icon (a black dot over a purple one, transparent background). It is the site's favicon. To use it as the GitHub social preview, upload `social-preview-1200x800.png` under Settings → General → Social preview.
