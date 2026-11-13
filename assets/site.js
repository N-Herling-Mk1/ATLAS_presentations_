// Landing page: renders window.CATALOG (written by tools/deck_tool.py) as cards, newest first.
// Decks stored here live in decks/<id>/. Decks with a `url` live in their own repo: the card links to that
// repo's GitHub Pages site, and its download paths are already absolute.
(function () {
  "use strict";
  const cat = window.CATALOG || { decks: [] };
  const key = (d) => d.updated || d.date || "";
  const decks = cat.decks.slice().sort((a, b) => key(b).localeCompare(key(a)));
  const list = document.getElementById("list");
  const q = document.getElementById("q");
  const tally = document.getElementById("tally");
  const empty = document.getElementById("empty");

  const el = (tag, cls, text) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  };
  const mb = (n) => (n ? (n / 1048576).toFixed(n < 10485760 ? 1 : 0) + " MB" : "");
  const niceDate = (s) => {
    if (!s) return "";
    const d = new Date(s + "T12:00:00");
    return isNaN(d) ? s : d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
  };
  const LABEL = { pdf: "PDF", pptx: "PPTX", html: "HTML" };
  const TITLE = { pdf: "One slide per page", pptx: "PowerPoint file with speaker notes", html: "The player in one self-contained file" };

  function card(d) {
    const remote = !!d.url;
    const base = remote ? "" : "decks/" + d.id + "/";
    const page = remote ? d.url : base + "index.html";     // explicit file: folder links fail when opened from disk
    const repoName = remote && d.repo ? d.repo.replace(/^https:\/\/github\.com\/[^/]+\//, "") : "";
    const li = el("li", "card" + (remote ? " remote" : ""));
    li.dataset.search = [d.title, d.subtitle, d.description, (d.tags || []).join(" "), d.date, repoName].join(" ").toLowerCase();

    const a = el("a", "thumb" + (d.thumb ? "" : " blank"));
    a.href = page; a.setAttribute("aria-label", "Open " + d.title);
    if (d.thumb) { const im = el("img"); im.src = base + d.thumb; im.alt = ""; im.loading = "lazy"; a.appendChild(im); }
    else a.appendChild(el("span", "", d.title));
    li.appendChild(a);

    const b = el("div", "body");
    const meta = [niceDate(d.date), d.slides + " slides"];
    if (d.updated && d.updated !== d.date) meta.splice(1, 0, "updated " + niceDate(d.updated));
    if (!d.slides) meta.pop();
    const m = el("div", "meta", meta.join(" · "));
    if (remote && d.repo) {
      const r = el("a", "repo", repoName + " ↗"); r.href = d.repo; r.target = "_blank"; r.rel = "noopener";
      r.title = "This deck lives in its own repository";
      m.append(" · "); m.appendChild(r);
    }
    b.appendChild(m);
    const h = el("h2"); const ha = el("a", "", d.title); ha.href = page; h.appendChild(ha); b.appendChild(h);
    if (d.subtitle) b.appendChild(el("p", "sub", d.subtitle));
    if (d.description) b.appendChild(el("p", "desc", d.description));
    if (d.tags && d.tags.length) {
      const t = el("div", "tags");
      d.tags.forEach((x) => t.appendChild(el("span", "tag", x)));
      b.appendChild(t);
    }
    const act = el("div", "actions");
    const play = el("a", "btn primary", "Present"); play.href = page; act.appendChild(play);
    ["pdf", "pptx", "html"].forEach((k) => {
      const f = d.files && d.files[k];
      if (!f) return;
      const x = el("a", "btn"); x.href = base + f.path; x.title = TITLE[k];
      if (remote) { x.target = "_blank"; x.rel = "noopener"; }  // browsers ignore `download` across origins
      else x.setAttribute("download", f.name);
      x.append(LABEL[k] + " "); x.appendChild(el("small", "", mb(f.bytes)));
      act.appendChild(x);
    });
    b.appendChild(act);
    li.appendChild(b);
    return li;
  }

  decks.forEach((d) => list.appendChild(card(d)));

  function filter() {
    const terms = q.value.toLowerCase().split(/\s+/).filter(Boolean);
    let shown = 0;
    list.querySelectorAll(".card").forEach((c) => {
      const ok = terms.every((t) => c.dataset.search.includes(t));
      c.hidden = !ok; if (ok) shown++;
    });
    tally.textContent = shown + (shown === decks.length ? "" : " of " + decks.length) + (decks.length === 1 ? " deck" : " decks");
    empty.hidden = shown !== 0 || decks.length === 0;
  }
  q.addEventListener("input", filter);
  filter();
})();
