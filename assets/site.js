// Landing page: renders window.CATALOG (written by tools/deck_tool.py) as cards, newest first.
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
    const base = "decks/" + d.id + "/";
    const page = base + "index.html";                      // explicit file: folder links fail when opened from disk
    const li = el("li", "card");
    li.dataset.search = [d.title, d.subtitle, d.description, (d.tags || []).join(" "), d.date].join(" ").toLowerCase();

    const a = el("a", "thumb");
    a.href = page; a.setAttribute("aria-label", "Open " + d.title);
    const im = el("img"); im.src = base + d.thumb; im.alt = ""; im.loading = "lazy";
    a.appendChild(im); li.appendChild(a);

    const b = el("div", "body");
    const meta = [niceDate(d.date), d.slides + " slides"];
    if (d.updated && d.updated !== d.date) meta.splice(1, 0, "updated " + niceDate(d.updated));
    b.appendChild(el("div", "meta", meta.join(" · ")));
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
      const x = el("a", "btn"); x.href = base + f.path; x.setAttribute("download", f.name); x.title = TITLE[k];
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
