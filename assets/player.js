// Shared slide player. Each deck folder holds index.html (generated), deck.js (window.DECK, generated),
// slides/, thumbs/ and downloads/. Works from file:// as well as GitHub Pages: no fetch, data comes in as a script.
(function () {
  "use strict";
  const D = window.DECK;
  if (!D || !D.slides || !D.slides.length) {
    document.body.textContent = "deck.js is missing or has no slides. Run: python tools/deck_tool.py build";
    return;
  }
  const N = D.slides.length;
  const $ = (id) => document.getElementById(id);
  const img = $("slide"), fill = $("fill"), count = $("count"), track = $("track");
  const ov = $("overview"), notes = $("notes"), notesBody = $("notes-body"), notesHead = $("notes-head");
  const dl = $("downloads"), help = $("help");
  const clamp = (i) => Math.min(N, Math.max(1, i | 0));
  const mb = (n) => (n ? (n / 1048576).toFixed(n < 10485760 ? 1 : 0) + " MB" : "");

  document.title = D.title;
  $("deck-title").textContent = D.title;
  const ar = D.width && D.height ? D.width + " / " + D.height : "16 / 9";
  img.style.aspectRatio = ar;
  document.documentElement.style.setProperty("--ar", ar);

  let cur = clamp(parseInt(location.hash.slice(1), 10) || 1);

  // ---- overview grid (thumbnails load lazily) ----
  D.slides.forEach((s, k) => {
    const b = document.createElement("button");
    b.type = "button"; b.className = "thumb"; b.dataset.i = k + 1; b.setAttribute("aria-label", "Slide " + (k + 1));
    const t = document.createElement("img"); t.loading = "lazy"; t.src = s.thumb || s.src; t.alt = "";
    const n = document.createElement("span"); n.textContent = k + 1;
    b.append(t, n);
    b.addEventListener("click", () => { show(k + 1); panel("overview", false); });
    ov.appendChild(b);
  });

  // ---- downloads menu ----
  const KINDS = [["pdf", "PDF", "one slide per page"], ["pptx", "PowerPoint (.pptx)", "with speaker notes"],
                 ["html", "HTML, single file", "this player, works offline"]];
  let any = false;
  KINDS.forEach(([k, label, hint]) => {
    const f = D.files && D.files[k];
    if (!f) return;
    any = true;
    const a = document.createElement("a");
    a.href = f.path; a.setAttribute("download", f.name); a.setAttribute("role", "menuitem"); a.title = f.name;
    const l = document.createElement("span"); l.textContent = label;
    const r = document.createElement("small"); r.textContent = hint + " · " + mb(f.bytes);
    a.append(l, r);
    a.addEventListener("click", () => panel("downloads", false));
    dl.appendChild(a);
  });
  if (!any) { const e = document.createElement("div"); e.className = "empty"; e.textContent = "No downloads for this deck."; dl.appendChild(e); }

  // ---- notes ----
  const hasNotes = D.slides.some((s) => s.notes && s.notes.trim());
  if (!hasNotes) $("btn-notes").title = "No speaker notes in this deck";
  function renderNotes() {
    notesHead.textContent = "Notes · slide " + cur + " / " + N;
    notesBody.replaceChildren();
    const raw = (D.slides[cur - 1].notes || "").trim();
    if (!raw) { const p = document.createElement("p"); p.className = "none"; p.textContent = "No notes on this slide."; notesBody.appendChild(p); return; }
    const cut = raw.indexOf("DATA:");                         // the data line, if the deck uses that convention
    const main = cut >= 0 ? raw.slice(0, cut).trim() : raw;
    const data = cut >= 0 ? raw.slice(cut + 5).trim().replace(/^Data:\s*/, "") : "";
    main.split(/\n+/).forEach((line) => { if (line.trim()) { const p = document.createElement("p"); p.textContent = line.trim(); notesBody.appendChild(p); } });
    if (data) {
      const d = document.createElement("div"); d.className = "data";
      const h = document.createElement("b"); h.textContent = "DATA";
      d.append(h, document.createTextNode(data));
      notesBody.appendChild(d);
    }
  }

  // ---- navigation ----
  const cache = new Map();
  function preload(i) {
    if (i < 1 || i > N || cache.has(i)) return;
    const p = new Image(); p.src = D.slides[i - 1].src; cache.set(i, p);
  }
  function show(i) {
    cur = clamp(i);
    img.src = D.slides[cur - 1].src;
    img.alt = "Slide " + cur + " of " + N + (hasNotes ? " (press N for the notes)" : "");
    fill.style.width = (100 * cur / N) + "%";
    count.textContent = cur + " / " + N;
    try { history.replaceState(null, "", "#" + cur); } catch (e) { /* some sandboxed viewers forbid this */ }
    ov.querySelectorAll(".thumb").forEach((t) => t.classList.toggle("on", +t.dataset.i === cur));
    if (!notes.hidden) renderNotes();
    preload(cur + 1); preload(cur + 2); preload(cur - 1);
  }

  // ---- panels ----
  const PANELS = { overview: [ov, "btn-grid"], notes: [notes, "btn-notes"], downloads: [dl, "btn-dl"], help: [help, "btn-help"] };
  function panel(name, force) {
    const [box, btn] = PANELS[name];
    const open = force === undefined ? box.hidden : force;
    if (open && (name === "downloads" || name === "help")) { panel("downloads", false); panel("help", false); }
    box.hidden = !open;
    $(btn).classList.toggle("on", open);
    $(btn).setAttribute("aria-expanded", String(open));
    if (name === "notes") { document.body.classList.toggle("notes-open", open); if (open) renderNotes(); }
    if (name === "overview" && open) { const on = ov.querySelector(".thumb.on"); if (on) on.scrollIntoView({ block: "nearest" }); }
  }
  function closeAll() { Object.keys(PANELS).forEach((k) => { if (k !== "notes") panel(k, false); }); }
  function fullscreen() {
    if (document.fullscreenElement) document.exitFullscreen();
    else if (document.documentElement.requestFullscreen) document.documentElement.requestFullscreen();
  }
  document.addEventListener("fullscreenchange", () => {
    document.body.classList.toggle("fs", !!document.fullscreenElement);
    $("btn-full").classList.toggle("on", !!document.fullscreenElement);
  });
  let idle;                                                                       // hide the bar in full screen when the mouse rests
  document.addEventListener("mousemove", () => {
    document.body.classList.remove("idle"); clearTimeout(idle);
    idle = setTimeout(() => document.body.classList.add("idle"), 2500);
  });

  $("prev").onclick = () => show(cur - 1);
  $("next").onclick = () => show(cur + 1);
  $("btn-grid").onclick = () => panel("overview");
  $("btn-notes").onclick = () => panel("notes");
  $("btn-dl").onclick = (e) => { e.stopPropagation(); panel("downloads"); };
  $("btn-help").onclick = (e) => { e.stopPropagation(); panel("help"); };
  $("btn-full").onclick = fullscreen;
  document.querySelectorAll("[data-close]").forEach((b) => b.addEventListener("click", () => panel(b.dataset.close, false)));
  img.addEventListener("click", () => show(cur + 1));
  track.addEventListener("click", (e) => {
    const r = track.getBoundingClientRect();
    show(Math.ceil(((e.clientX - r.left) / r.width) * N));
  });
  document.addEventListener("click", (e) => {                                     // click outside closes popovers
    if (!dl.hidden && !dl.contains(e.target)) panel("downloads", false);
    if (!help.hidden && !help.contains(e.target)) panel("help", false);
  });
  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;                                // leave Ctrl+P etc. alone
    const k = e.key;
    if (["ArrowRight", "PageDown", " "].includes(k)) { e.preventDefault(); show(cur + 1); }
    else if (["ArrowLeft", "PageUp"].includes(k)) { e.preventDefault(); show(cur - 1); }
    else if (k === "Home") show(1);
    else if (k === "End") show(N);
    else if (k === "g" || k === "G") panel("overview");
    else if (k === "n" || k === "N") panel("notes");
    else if (k === "d" || k === "D") panel("downloads");
    else if (k === "f" || k === "F") fullscreen();
    else if (k === "?") panel("help");
    else if (k === "Escape") closeAll();
  });
  window.addEventListener("hashchange", () => { const i = parseInt(location.hash.slice(1), 10); if (i && i !== cur) show(i); });
  let x0 = null;                                                                  // swipe on touch screens
  document.addEventListener("touchstart", (e) => { x0 = e.touches[0].clientX; }, { passive: true });
  document.addEventListener("touchend", (e) => {
    if (x0 === null) return; const dx = e.changedTouches[0].clientX - x0; x0 = null;
    if (Math.abs(dx) > 40) show(cur + (dx < 0 ? 1 : -1));
  });

  // Print copies (Ctrl+P = one slide per page). Added after load so the current slide comes first.
  window.addEventListener("load", () => setTimeout(() => {
    D.slides.forEach((s, k) => {
      const p = document.createElement("img"); p.src = s.src; p.className = "print-slide"; p.alt = "Slide " + (k + 1);
      document.body.appendChild(p);
    });
  }, 1200));

  show(cur);
})();
