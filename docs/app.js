"use strict";

const $ = (id) => document.getElementById(id);
const statusEl = $("status");
const setStatus = (m) => { statusEl.textContent = m; };

$("date").textContent = new Date().toLocaleDateString(undefined, {
  weekday: "long", year: "numeric", month: "long", day: "numeric",
});

let pyodide = null;
let runFn = null;     // Python pips.webapi.run, as a callable PyProxy
let solveFn = null;   // Python pips.webapi.solve_structured
let busy = false;
let lastStructure = null; // last parsed structure (for the review panel)

async function boot() {
  try {
    pyodide = await loadPyodide();
    setStatus("Loading numpy, scipy and Pillow…");
    await pyodide.loadPackage(["numpy", "scipy", "Pillow"]);

    setStatus("Loading the Pips parser/solver…");
    pyodide.FS.mkdirTree("/pkg/pips");
    const files = await (await fetch("pysrc/manifest.json")).json();
    for (const name of files) {
      const txt = await (await fetch("pysrc/pips/" + name)).text();
      pyodide.FS.writeFile("/pkg/pips/" + name, txt);
    }
    pyodide.runPython("import sys; sys.path.insert(0, '/pkg')");
    runFn = pyodide.runPython("from pips.webapi import run\nrun");
    solveFn = pyodide.runPython(
      "from pips.webapi import solve_structured\nsolve_structured");

    setStatus("Ready. Pick Easy / Medium / Hard, upload a screenshot, "
      + "or paste an image URL.");
    for (const el of document.querySelectorAll("button,#file,#url"))
      el.disabled = false;
  } catch (e) {
    setStatus("Failed to start: " + e + " (try reloading).");
    console.error(e);
  }
}

const LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz";

function regionLetter(rid) { return LETTERS[rid % 52]; }

function rgbCss(c) { return `rgb(${c[0]},${c[1]},${c[2]})`; }

function flagsByItem(flags) {
  const m = { region: new Map(), domino: new Map(), cell: new Map() };
  for (const f of flags) m[f.kind].set(f.id, f.reasons);
  return m;
}

function populateReview(structure, flags) {
  const byItem = flagsByItem(flags);
  const KINDS = [
    ["NONE", "(free)"],
    ["SUM_EQ", "sum ="],
    ["SUM_LT", "sum <"],
    ["SUM_GT", "sum >"],
    ["ALL_EQUAL", "= (all equal)"],
    ["ALL_DIFFERENT", "≠ (all different)"],
  ];

  const rrows = ['<table class="rev"><thead><tr>' +
    '<th>Region</th><th>Constraint</th><th>Target</th>' +
    '<th>Why flagged</th></tr></thead><tbody>'];
  for (const r of structure.regions) {
    const reasons = byItem.region.get(r.id);
    const flagged = reasons ? " class='flagged'" : "";
    const showTarget = ["SUM_EQ", "SUM_LT", "SUM_GT"].includes(r.kind);
    const opts = KINDS.map(([k, lbl]) =>
      `<option value="${k}"${k === r.kind ? " selected" : ""}>${lbl}</option>`
    ).join("");
    rrows.push(
      `<tr${flagged} data-rid="${r.id}">` +
      `<td><span class="swatch" style="background:${rgbCss(r.color)}"></span>` +
      `${regionLetter(r.id)} <span class="muted">(${r.n_cells} cell${r.n_cells === 1 ? "" : "s"})</span></td>` +
      `<td><select class="rv-kind">${opts}</select></td>` +
      `<td><input class="rv-target" type="number" min="0" max="30" ` +
      `value="${r.target ?? ""}" ${showTarget ? "" : "disabled"}></td>` +
      `<td class="flag-why">${reasons ? reasons.join("; ") : ""}</td>` +
      "</tr>");
  }
  rrows.push("</tbody></table>");
  $("review-regions").innerHTML = rrows.join("");

  const droots = [];
  for (const d of structure.dominoes) {
    const reasons = byItem.domino.get(d.id);
    const flagged = reasons ? " flagged" : "";
    droots.push(
      `<span class="dom-edit${flagged}" data-id="${d.id}" ` +
      `title="${reasons ? reasons.join("; ") : ""}">` +
      `<input class="rv-a" type="number" min="0" max="6" value="${d.a}">` +
      `<span class="sep">|</span>` +
      `<input class="rv-b" type="number" min="0" max="6" value="${d.b}">` +
      "</span>");
  }
  $("review-dominoes").innerHTML = droots.join("");

  // working copy of cell edits (only stores the changed fields)
  workingCells = new Map();
  for (const c of structure.cells) {
    workingCells.set(c.id, { rid: c.rid, removed: false });
  }
  populateCells(structure, byItem);

  // disable target input when kind isn't a SUM_*
  for (const sel of document.querySelectorAll("select.rv-kind")) {
    sel.addEventListener("change", () => {
      const tgt = sel.closest("tr").querySelector("input.rv-target");
      tgt.disabled = !["SUM_EQ", "SUM_LT", "SUM_GT"].includes(sel.value);
    });
  }
}

function populateCells(structure, byItem) {
  const GAP = 1000;
  const blocks = [];
  const clusters = {};
  for (const c of structure.cells) {
    const k = Math.floor(c.r / GAP);
    (clusters[k] = clusters[k] || []).push(c);
  }
  for (const k of Object.keys(clusters).sort((a, b) => +a - +b)) {
    const cs = clusters[k];
    const rs = cs.map((c) => c.r % GAP);
    const cols = cs.map((c) => c.c);
    const minR = Math.min(...rs), maxR = Math.max(...rs);
    const minC = Math.min(...cols), maxC = Math.max(...cols);
    const cellMap = new Map();
    for (const c of cs) cellMap.set(`${c.r % GAP}_${c.c}`, c);
    let html = `<div class="cells-block"><div class="cells-grid" ` +
      `style="grid-template-columns:repeat(${maxC - minC + 1},32px)">`;
    for (let r = minR; r <= maxR; r++) {
      for (let c = minC; c <= maxC; c++) {
        const cell = cellMap.get(`${r}_${c}`);
        if (cell) {
          const reg = structure.regions.find((rr) => rr.id === cell.rid);
          const color = reg ? rgbCss(reg.color) : "#eee";
          const flagged = byItem.cell.has(cell.id) ? " flagged" : "";
          html += `<button class="cell-btn${flagged}" data-id="${cell.id}" ` +
            `style="background:${color}">${regionLetter(cell.rid)}</button>`;
        } else {
          html += '<span></span>';
        }
      }
    }
    html += "</div></div>";
    blocks.push(html);
  }
  $("review-cells").innerHTML = blocks.join("");

  const rids = structure.regions.map((r) => r.id).sort((a, b) => a - b);
  for (const btn of document.querySelectorAll(".cell-btn")) {
    const update = () => {
      const cell = workingCells.get(btn.dataset.id);
      if (cell.removed) {
        btn.classList.add("removed");
        btn.style.background = "#eee";
        btn.textContent = "·";
      } else {
        btn.classList.remove("removed");
        const reg = structure.regions.find((rr) => rr.id === cell.rid);
        btn.style.background = reg ? rgbCss(reg.color) : "#eee";
        btn.textContent = regionLetter(cell.rid);
      }
    };
    btn.addEventListener("click", (ev) => {
      const cell = workingCells.get(btn.dataset.id);
      if (cell.removed) cell.removed = false;
      else {
        const idx = rids.indexOf(cell.rid);
        cell.rid = rids[(idx + 1) % rids.length];
      }
      update();
    });
    btn.addEventListener("contextmenu", (ev) => {
      ev.preventDefault();
      const cell = workingCells.get(btn.dataset.id);
      cell.removed = !cell.removed;
      update();
    });
  }
}

let workingCells = new Map();

function collectReview() {
  const out = {
    cells: lastStructure.cells
      .map((c) => ({ ...c, ...(workingCells.get(c.id) || {}) }))
      .filter((c) => !c.removed),
    regions: [],
    dominoes: [],
  };
  for (const r of lastStructure.regions) {
    const row = document.querySelector(`tr[data-rid="${r.id}"]`);
    const kind = row.querySelector("select.rv-kind").value;
    const targetRaw = row.querySelector("input.rv-target").value;
    const target = (kind === "SUM_EQ" || kind === "SUM_LT" ||
      kind === "SUM_GT") && targetRaw !== ""
      ? parseInt(targetRaw, 10) : null;
    out.regions.push({ ...r, kind, target });
  }
  for (const d of lastStructure.dominoes) {
    const span = document.querySelector(`.dom-edit[data-id="${d.id}"]`);
    out.dominoes.push({
      ...d,
      a: parseInt(span.querySelector("input.rv-a").value, 10) || 0,
      b: parseInt(span.querySelector("input.rv-b").value, 10) || 0,
    });
  }
  return out;
}

function showSolution(res) {
  $("parsed").textContent = res.parsed;
  $("solution").textContent = res.solution;
  try {
    _playLayout = res.layout;
    _progressStats = progressStats(res.layout);
    _playCount = totalPlacements(res.layout);   // full board to start
    stopPlayback();
    renderPlayback();
    $("playslider").max = totalPlacements(res.layout);
    $("playcontrols").classList.remove("hidden");
    $("progress-chart").classList.remove("hidden");
    $("lh").textContent = res.layout.n_h;
    $("lv").textContent = res.layout.n_v;
    $("legend").classList.remove("hidden");
  } catch (e) {
    $("svgwrap").innerHTML =
      '<p class="muted">(graphical view unavailable)</p>';
    console.error(e);
  }
  $("b-parse").textContent = "parse " + (res.parse_ms ?? "—") + " ms";
  $("b-solve").textContent = "solve " + res.solve_ms + " ms";
  $("b-grid").textContent =
    res.n_cells + " cells · " + res.n_dominoes + " dominoes · " +
    res.n_regions + " regions";
  const v = $("b-verified");
  if (res.solved && res.verified) {
    v.textContent = "solution verified ✓"; v.className = "badge ok";
  } else if (!res.valid && res.error) {
    v.textContent = "puzzle invalid: " + res.error; v.className = "badge";
  } else {
    v.textContent = res.solved ? "solved (unverified)" : "no solution";
    v.className = "badge";
  }
  $("badges").classList.remove("hidden");
}

async function solveBytes(u8, previewBlobType) {
  if (!runFn || busy) return;
  busy = true;
  $("badges").classList.add("hidden");
  $("review").classList.add("hidden");
  try {
    const url = URL.createObjectURL(new Blob([u8], {
      type: previewBlobType || "image/png",
    }));
    $("preview").src = url;

    setStatus("Parsing the screenshot…");
    $("parsed").textContent = "…";
    $("solution").textContent = "…";

    pyodide.FS.writeFile("/tmp/in.png", u8);
    await new Promise((r) => setTimeout(r, 30));

    const proxy = runFn();
    const res = proxy.toJs({ dict_converter: Object.fromEntries });
    proxy.destroy();
    lastStructure = res.structure;

    if (res.needs_review) {
      populateReview(res.structure, res.flags || []);
      $("review").classList.remove("hidden");
      $("review").scrollIntoView({ behavior: "smooth", block: "start" });
      setStatus("Parser flagged " + (res.flags || []).length +
        " item(s) for review — confirm or correct, then press Solve.");
    } else {
      res.parse_ms = res.parse_ms;
      showSolution(res);
      setStatus("Done.");
    }
  } catch (e) {
    setStatus("Error: " + e);
    $("solution").textContent = String(e);
    console.error(e);
  } finally {
    busy = false;
  }
}

async function solveFromReview() {
  if (!solveFn || !lastStructure) return;
  setStatus("Solving with your confirmed values…");
  await new Promise((r) => setTimeout(r, 20));
  try {
    const edited = collectReview();
    const proxy = solveFn(pyodide.toPy(edited));
    const res = proxy.toJs({ dict_converter: Object.fromEntries });
    proxy.destroy();
    lastStructure = res.structure;
    showSolution(res);
    $("review").classList.add("hidden");
    setStatus("Done.");
  } catch (e) {
    setStatus("Solve failed: " + e);
    console.error(e);
  }
}

function buildSVG(layout, opts = {}) {
  const CS = 46, INS = 5, PAD = 14, GY = 26;
  const H_COL = "#2f6f9f", V_COL = "#c8762a";
  // when opts.count is set, only the first `count` placements (across all
  // clusters in layout order) are drawn — used by the playback animation.
  const limit = (opts.count === undefined) ? Infinity : opts.count;

  let totalW = 0, totalH = PAD;
  const offsets = [];
  for (const cl of layout.clusters) {
    const w = (cl.maxc - cl.minc + 1) * CS;
    const h = (cl.maxr - cl.minr + 1) * CS;
    offsets.push(totalH);
    totalH += h + GY;
    totalW = Math.max(totalW, w);
  }
  totalH += PAD - GY;
  totalW += 2 * PAD;

  const parts = [`<svg viewBox="0 0 ${totalW} ${totalH}" ` +
    `xmlns="http://www.w3.org/2000/svg" font-family="ui-monospace,` +
    `Menlo,Consolas,monospace">`];

  let placed = 0;
  layout.clusters.forEach((cl, ci) => {
    const oy = offsets[ci];
    const cx = (c) => PAD + (c - cl.minc) * CS;
    const cy = (r) => oy + (r - cl.minr) * CS;

    for (const cell of cl.cells) {
      const [r, g, b] = cell.color;
      parts.push(`<rect x="${cx(cell.c)}" y="${cy(cell.r)}" ` +
        `width="${CS}" height="${CS}" rx="7" ` +
        `fill="rgb(${r},${g},${b})" fill-opacity="0.55" ` +
        `stroke="#e3ddd5"/>`);
    }

    for (const p of cl.placements) {
      if (placed >= limit) break;
      placed++;
      const horiz = p.orient === "H";
      const r0 = Math.min(p.a[0], p.b[0]), c0 = Math.min(p.a[1], p.b[1]);
      const x = cx(c0) + INS, y = cy(r0) + INS;
      const w = (horiz ? 2 : 1) * CS - 2 * INS;
      const h = (horiz ? 1 : 2) * CS - 2 * INS;
      const col = horiz ? H_COL : V_COL;
      parts.push(`<rect x="${x}" y="${y}" width="${w}" height="${h}" ` +
        `rx="9" fill="#fdfdfb" fill-opacity="0.65" stroke="${col}" ` +
        `stroke-width="3"/>`);
      if (horiz)
        parts.push(`<line x1="${x + w / 2}" y1="${y + 4}" ` +
          `x2="${x + w / 2}" y2="${y + h - 4}" stroke="${col}" ` +
          `stroke-width="1.5" stroke-dasharray="3 3"/>`);
      else
        parts.push(`<line x1="${x + 4}" y1="${y + h / 2}" ` +
          `x2="${x + w - 4}" y2="${y + h / 2}" stroke="${col}" ` +
          `stroke-width="1.5" stroke-dasharray="3 3"/>`);
      const put = (cc, rr, val) => parts.push(
        `<text x="${cx(cc) + CS / 2}" y="${cy(rr) + CS / 2}" ` +
        `font-size="20" font-weight="700" fill="#26211d" ` +
        `text-anchor="middle" dominant-baseline="central">${val}</text>`);
      put(p.a[1], p.a[0], p.va);
      put(p.b[1], p.b[0], p.vb);
    }
  });
  parts.push("</svg>");
  return parts.join("");
}

function totalPlacements(layout) {
  let n = 0;
  for (const cl of layout.clusters) n += cl.placements.length;
  return n;
}

function progressStats(layout) {
  // collect placements in playback order; record, after each step, how
  // many regions have *all* their cells covered (= satisfied since the
  // solver only commits to feasible placements).
  const placements = [];
  for (const cl of layout.clusters) for (const p of cl.placements) placements.push(p);
  const regionCells = new Map();
  for (const cl of layout.clusters) {
    for (const cell of cl.cells) {
      const k = cell.region;
      if (!regionCells.has(k)) regionCells.set(k, []);
      regionCells.get(k).push(`${cell.r}_${cell.c}`);
    }
  }
  const totalRegions = regionCells.size;
  const covered = new Set();
  const stats = [];
  for (let n = 0; n <= placements.length; n++) {
    let satisfied = 0;
    for (const cells of regionCells.values()) {
      if (cells.every((id) => covered.has(id))) satisfied++;
    }
    stats.push({ step: n, satisfied, covered: covered.size });
    if (n < placements.length) {
      const p = placements[n];
      covered.add(`${p.a[0]}_${p.a[1]}`);
      covered.add(`${p.b[0]}_${p.b[1]}`);
    }
  }
  return { stats, totalRegions, totalCells: covered.size };
}

function buildProgressChart(stats, totalRegions, currentStep) {
  const W = 340, H = 90, PAD = 22;
  const maxN = stats.stats.length - 1;
  const px = (i) => PAD + (i / Math.max(1, maxN)) * (W - 2 * PAD);
  const py = (v) => H - PAD -
    (v / Math.max(1, totalRegions)) * (H - 2 * PAD);
  let poly = "";
  for (let i = 0; i < stats.stats.length; i++)
    poly += (i ? " " : "") + px(i) + "," + py(stats.stats[i].satisfied);
  const cx = px(currentStep);
  const cv = stats.stats[currentStep].satisfied;
  const cy = py(cv);
  return `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" ` +
    `font-family="ui-monospace,Menlo,monospace" font-size="11" ` +
    `fill="#5a3d86">` +
    // y-axis labels
    `<text x="2" y="${py(0) + 3}" fill="#7a7068">0</text>` +
    `<text x="2" y="${py(totalRegions) + 3}" fill="#7a7068">${totalRegions}</text>` +
    `<text x="${W/2}" y="${H - 3}" text-anchor="middle" ` +
    `fill="#7a7068">dominoes placed →</text>` +
    `<text transform="rotate(-90 12 ${H/2})" x="12" y="${H/2}" ` +
    `text-anchor="middle" fill="#7a7068">regions satisfied</text>` +
    // axes
    `<line x1="${PAD}" y1="${py(0)}" x2="${W - PAD}" y2="${py(0)}" ` +
    `stroke="#e3ddd5"/>` +
    `<line x1="${PAD}" y1="${py(0)}" x2="${PAD}" y2="${py(totalRegions)}" ` +
    `stroke="#e3ddd5"/>` +
    // data line
    `<polyline points="${poly}" fill="none" stroke="#7a4fb0" ` +
    `stroke-width="2"/>` +
    // current-step marker
    `<line x1="${cx}" y1="${py(0)}" x2="${cx}" y2="${py(totalRegions)}" ` +
    `stroke="#d68b00" stroke-dasharray="3 3"/>` +
    `<circle cx="${cx}" cy="${cy}" r="4" fill="#d68b00"/>` +
    `<text x="${cx + 6}" y="${cy - 6}" fill="#a06400">` +
    `${cv}/${totalRegions}</text>` +
    "</svg>";
}

let _progressStats = null;

let _playTimer = null;
let _playLayout = null;
let _playCount = 0;
function stopPlayback() {
  if (_playTimer) { clearInterval(_playTimer); _playTimer = null; }
  $("playbtn").textContent = "▶ Play";
}
function renderPlayback() {
  if (!_playLayout) return;
  $("svgwrap").innerHTML = buildSVG(_playLayout, { count: _playCount });
  const n = totalPlacements(_playLayout);
  $("playstep").textContent = _playCount + " / " + n;
  $("playslider").value = _playCount;
  if (_progressStats) {
    $("progress-chart").innerHTML = buildProgressChart(
      _progressStats, _progressStats.totalRegions, _playCount);
  }
}
function startPlayback() {
  if (!_playLayout) return;
  const n = totalPlacements(_playLayout);
  if (_playCount >= n) _playCount = 0;
  $("playbtn").textContent = "⏸ Pause";
  _playTimer = setInterval(() => {
    _playCount += 1;
    renderPlayback();
    if (_playCount >= n) stopPlayback();
  }, 380);
}

async function loadFromFetch(path) {
  setStatus("Fetching " + path + " …");
  const buf = await (await fetch(path)).arrayBuffer();
  return new Uint8Array(buf);
}

for (const btn of document.querySelectorAll("button.puz")) {
  btn.addEventListener("click", async () => {
    try {
      const u8 = await loadFromFetch("puzzles/" + btn.dataset.file);
      await solveBytes(u8);
    } catch (e) { setStatus("Could not load puzzle: " + e); }
  });
}

$("file").addEventListener("change", async (ev) => {
  const f = ev.target.files[0];
  if (!f) return;
  const u8 = new Uint8Array(await f.arrayBuffer());
  await solveBytes(u8, f.type);
});

$("playbtn").addEventListener("click", () => {
  if (_playTimer) stopPlayback();
  else startPlayback();
});
$("playreset").addEventListener("click", () => {
  stopPlayback();
  _playCount = 0;
  renderPlayback();
});
$("playslider").addEventListener("input", (ev) => {
  stopPlayback();
  _playCount = parseInt(ev.target.value, 10);
  renderPlayback();
});
$("review-solve").addEventListener("click", solveFromReview);
$("review-cancel").addEventListener("click", () => {
  if (lastStructure) populateReview(lastStructure, []); // discard edits
});

$("loadurl").addEventListener("click", async () => {
  const u = $("url").value.trim();
  if (!u) return;
  try {
    setStatus("Fetching image…");
    const r = await fetch(u, { mode: "cors" });
    const u8 = new Uint8Array(await r.arrayBuffer());
    await solveBytes(u8);
  } catch (e) {
    setStatus("Could not fetch that URL (likely blocked by CORS). "
      + "Download the image and use “Upload screenshot”.");
  }
});

boot();
