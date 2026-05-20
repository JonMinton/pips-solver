"use strict";

const $ = (id) => document.getElementById(id);
const setStatus = (m) => { $("status").textContent = m; };
const setMsg = (m) => { $("game-msg").textContent = m; };
const LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz";

let pyodide = null, runFn = null, solveFn = null;
let layout = null;            // from webapi.run().layout
let regions = null;           // [{id,kind,target,color,cells:[cellId,...]}]
let cells = null;             // [{id,r,c,rid,color}]
let dominoes = null;          // [{id,a,b,used:false}]
let placements = [];          // [{id,a,b,cellA,cellB,orient}]
let energyHistory = [];       // [{step, energy}]
let selectedDomId = null;
let orientation = "H";

async function boot() {
  try {
    pyodide = await loadPyodide();
    setStatus("Loading numpy, scipy and Pillow …");
    await pyodide.loadPackage(["numpy", "scipy", "Pillow"]);
    setStatus("Loading the Pips parser …");
    pyodide.FS.mkdirTree("/pkg/pips");
    const files = await (await fetch("pysrc/manifest.json")).json();
    for (const f of files) {
      const txt = await (await fetch("pysrc/pips/" + f)).text();
      pyodide.FS.writeFile("/pkg/pips/" + f, txt);
    }
    pyodide.runPython("import sys; sys.path.insert(0, '/pkg')");
    runFn = pyodide.runPython("from pips.webapi import run\nrun");
    solveFn = pyodide.runPython(
      "from pips.webapi import solve_structured\nsolve_structured");
    for (const b of document.querySelectorAll("button.puz")) b.disabled = false;
    setStatus("Ready. Pick a puzzle to begin.");
  } catch (e) {
    setStatus("Failed to start: " + e);
    console.error(e);
  }
}

async function loadPuzzle(file) {
  setStatus("Parsing " + file + " …");
  const buf = await (await fetch("puzzles/" + file)).arrayBuffer();
  pyodide.FS.writeFile("/tmp/in.png", new Uint8Array(buf));
  await new Promise((r) => setTimeout(r, 30));
  const proxy = runFn();
  const res = proxy.toJs({ dict_converter: Object.fromEntries });
  proxy.destroy();

  layout = res.layout;
  cells = res.structure.cells;
  regions = res.structure.regions.map((r) => ({
    id: r.id, kind: r.kind, target: r.target, color: r.color, cells: [],
  }));
  for (const c of cells) {
    const r = regions.find((rr) => rr.id === c.rid);
    if (r) r.cells.push(`${c.r}_${c.c}`);
  }
  dominoes = res.structure.dominoes.map((d) => ({
    id: d.id, a: d.a, b: d.b, used: false,
  }));
  placements = [];
  selectedDomId = null;
  resetEnergyHistory();
  $("game").classList.remove("hidden");
  renderAll();
  setStatus(`Loaded. Place all ${dominoes.length} dominoes to satisfy ` +
    "every constraint.");
}

function resetEnergyHistory() {
  energyHistory = [{ step: 0, energy: computeEnergy() }];
}

function computeEnergy() {
  // build current cell -> value
  const v = {};
  for (const p of placements) { v[p.cellA] = p.a; v[p.cellB] = p.b; }
  let total = 0;
  for (const r of regions) {
    const vals = r.cells.map((cid) => v[cid]).filter((x) => x !== undefined);
    total += violation(r.kind, r.target, vals,
                       vals.length === r.cells.length);
  }
  return total;
}

function violation(kind, target, vals, completed) {
  if (kind === "NONE") return 0;
  const s = vals.reduce((a, b) => a + b, 0);
  if (completed) {
    if (kind === "ALL_EQUAL") {
      if (!vals.length) return 0;
      const m = mode(vals);
      return vals.filter((v) => v !== m).length;
    }
    if (kind === "ALL_DIFFERENT") return vals.length - new Set(vals).size;
    if (kind === "SUM_EQ") return Math.abs(s - target);
    if (kind === "SUM_LT") return Math.max(0, s - (target - 1));
    if (kind === "SUM_GT") return Math.max(0, (target + 1) - s);
  } else {
    // partial — only count "already broken"
    if (kind === "ALL_EQUAL") {
      if (vals.length <= 1) return 0;
      return vals.filter((v) => v !== vals[0]).length;
    }
    if (kind === "ALL_DIFFERENT") return vals.length - new Set(vals).size;
    if (kind === "SUM_EQ") return s > target ? s - target : 0;
    if (kind === "SUM_LT") return s >= target ? s - (target - 1) : 0;
    if (kind === "SUM_GT") return 0;       // can still grow into range
  }
  return 0;
}

function mode(arr) {
  const counts = new Map();
  for (const v of arr) counts.set(v, (counts.get(v) || 0) + 1);
  let best = arr[0], n = 0;
  for (const [v, c] of counts) if (c > n) { best = v; n = c; }
  return best;
}

const CS = 46, INS = 5, PAD = 14, GY = 26;

function buildBoardSVG() {
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

  const valBy = {};
  for (const p of placements) { valBy[p.cellA] = p.a; valBy[p.cellB] = p.b; }

  let svg = `<svg viewBox="0 0 ${totalW} ${totalH}" ` +
    `xmlns="http://www.w3.org/2000/svg" id="board-svg" ` +
    `font-family="ui-monospace,Menlo,monospace">`;
  layout.clusters.forEach((cl, ci) => {
    const oy = offsets[ci];
    const cxf = (c) => PAD + (c - cl.minc) * CS;
    const cyf = (r) => oy + (r - cl.minr) * CS;
    for (const cell of cl.cells) {
      const cid = `${cell.r}_${cell.c}`;
      const reg = regions.find((rr) => rr.id === cell.region);
      const col = reg ? `rgb(${reg.color[0]},${reg.color[1]},${reg.color[2]})`
                      : "#ccc";
      svg += `<rect class="play-cell" x="${cxf(cell.c)}" y="${cyf(cell.r)}" ` +
        `width="${CS}" height="${CS}" rx="7" fill="${col}" ` +
        `fill-opacity="0.55" stroke="#e3ddd5" ` +
        `data-cid="${cid}" data-r="${cell.r}" data-c="${cell.c}" ` +
        `style="cursor:pointer"/>`;
    }
    // domino outlines
    for (const p of placements) {
      const cell = cl.cells.find((c) => `${c.r}_${c.c}` === p.cellA);
      if (!cell) continue;
      const horiz = p.orient === "H";
      const r0 = Math.min(p.aR, p.bR), c0 = Math.min(p.aC, p.bC);
      const x = cxf(c0) + INS, y = cyf(r0) + INS;
      const w = (horiz ? 2 : 1) * CS - 2 * INS;
      const h = (horiz ? 1 : 2) * CS - 2 * INS;
      const col = horiz ? "#2f6f9f" : "#c8762a";
      svg += `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="9" ` +
        `fill="#fdfdfb" fill-opacity="0.7" stroke="${col}" ` +
        `stroke-width="3" pointer-events="none"/>`;
    }
    // pip values
    for (const cell of cl.cells) {
      const cid = `${cell.r}_${cell.c}`;
      if (valBy[cid] === undefined) continue;
      svg += `<text x="${cxf(cell.c) + CS / 2}" y="${cyf(cell.r) + CS / 2}" ` +
        `font-size="20" font-weight="700" fill="#26211d" ` +
        `text-anchor="middle" dominant-baseline="central" ` +
        `pointer-events="none">${valBy[cid]}</text>`;
    }
  });
  svg += "</svg>";
  return svg;
}

function buildEnergyChart() {
  const W = 320, H = 110, P = 22;
  const maxE = Math.max(3, ...energyHistory.map((s) => s.energy));
  const maxN = Math.max(1, energyHistory.length - 1, dominoes.length);
  const px = (i) => P + (i / maxN) * (W - 2 * P);
  const py = (e) => H - P - (e / maxE) * (H - 2 * P);
  let poly = "";
  for (let i = 0; i < energyHistory.length; i++)
    poly += (i ? " " : "") + px(energyHistory[i].step) + "," +
      py(energyHistory[i].energy);
  const cur = energyHistory[energyHistory.length - 1];
  return `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" ` +
    `font-family="ui-monospace,Menlo,monospace" font-size="11">` +
    `<text x="2" y="${py(0) + 3}" fill="#7a7068">0</text>` +
    `<text x="2" y="${py(maxE) + 3}" fill="#7a7068">${maxE}</text>` +
    `<text x="${W/2}" y="${H - 3}" text-anchor="middle" fill="#7a7068">` +
    `move →</text>` +
    `<text transform="rotate(-90 12 ${H/2})" x="12" y="${H/2}" ` +
    `text-anchor="middle" fill="#7a7068">energy</text>` +
    `<line x1="${P}" y1="${py(0)}" x2="${W - P}" y2="${py(0)}" ` +
    `stroke="#e3ddd5"/>` +
    `<line x1="${P}" y1="${py(0)}" x2="${P}" y2="${py(maxE)}" ` +
    `stroke="#e3ddd5"/>` +
    `<polyline points="${poly}" fill="none" stroke="#7a4fb0" ` +
    `stroke-width="2"/>` +
    `<circle cx="${px(cur.step)}" cy="${py(cur.energy)}" r="4" ` +
    `fill="${cur.energy === 0 ? '#2f8f4e' : '#d68b00'}"/>` +
    `<text x="${px(cur.step) + 6}" y="${py(cur.energy) - 6}" ` +
    `fill="${cur.energy === 0 ? '#2f8f4e' : '#a06400'}">` +
    `${cur.energy}</text>` +
    "</svg>";
}

function buildRegionStatus() {
  // build value map
  const v = {};
  for (const p of placements) { v[p.cellA] = p.a; v[p.cellB] = p.b; }
  const rows = [];
  for (const r of regions) {
    const vals = r.cells.map((cid) => v[cid]).filter((x) => x !== undefined);
    const completed = vals.length === r.cells.length;
    const vio = violation(r.kind, r.target, vals, completed);
    let state = "empty";
    if (vals.length && vio === 0 && !completed) state = "partial-ok";
    if (vals.length && vio > 0 && !completed) state = "partial-bad";
    if (completed && vio === 0) state = "done";
    if (completed && vio > 0) state = "broken";
    const kindLbl = describeKind(r.kind, r.target);
    const valStr = vals.length ? vals.join(",") : "—";
    rows.push(
      `<div class="rs-row rs-${state}">` +
      `<span class="swatch" style="background:rgb(${r.color.join(",")})"></span>` +
      `<b>${LETTERS[r.id % 52]}</b> <span class="muted">${kindLbl}</span> ` +
      `<span class="rs-vals">[${valStr}]</span>` +
      `</div>`);
  }
  return rows.join("");
}

function describeKind(kind, target) {
  return {
    NONE: "(free)",
    ALL_EQUAL: "= (all equal)",
    ALL_DIFFERENT: "≠ (all different)",
    SUM_EQ: "sum = " + target,
    SUM_LT: "sum < " + target,
    SUM_GT: "sum > " + target,
  }[kind] || kind;
}

function buildPalette() {
  let html = "";
  for (const d of dominoes) {
    const cls = "pal-dom" + (d.used ? " used" : "") +
                (d.id === selectedDomId ? " selected" : "");
    html += `<button class="${cls}" data-id="${d.id}" ` +
      (d.used ? "disabled" : "") + `>` +
      `<span class="pip">${d.a}</span><span class="sep">|</span>` +
      `<span class="pip">${d.b}</span></button>`;
  }
  return html;
}

function renderAll() {
  $("board-wrap").innerHTML = buildBoardSVG();
  $("energy-chart").innerHTML = buildEnergyChart();
  $("region-status").innerHTML = buildRegionStatus();
  $("palette").innerHTML = buildPalette();
  bindBoardClicks();
  bindPaletteClicks();
}

function bindBoardClicks() {
  for (const r of document.querySelectorAll(".play-cell")) {
    r.addEventListener("click", () => tryPlace(r.dataset.r, r.dataset.c));
  }
}

function bindPaletteClicks() {
  for (const b of document.querySelectorAll(".pal-dom")) {
    b.addEventListener("click", () => {
      selectedDomId = parseInt(b.dataset.id, 10);
      $("palette").innerHTML = buildPalette();
      bindPaletteClicks();
      setMsg("Selected domino [" +
        dominoes[selectedDomId].a + "|" + dominoes[selectedDomId].b +
        "]. Click a cell to place it (a→clicked, b→neighbour in selected " +
        (orientation === "H" ? "horizontal" : "vertical") + " direction).");
    });
  }
}

function tryPlace(rStr, cStr) {
  const r = parseInt(rStr, 10), c = parseInt(cStr, 10);
  if (selectedDomId === null) {
    setMsg("Pick a domino from the palette first.");
    return;
  }
  const dom = dominoes[selectedDomId];
  if (dom.used) {
    setMsg("That domino is already placed; pick another.");
    return;
  }
  const dr = orientation === "V" ? 1 : 0;
  const dc = orientation === "H" ? 1 : 0;
  const cellA = `${r}_${c}`, cellB = `${r + dr}_${c + dc}`;
  // both cells must exist on the board
  const cidSet = new Set(cells.map((cc) => cc.id));
  if (!cidSet.has(cellA) || !cidSet.has(cellB)) {
    setMsg("That domino would fall off the board in the " +
      (orientation === "H" ? "horizontal" : "vertical") + " direction.");
    return;
  }
  // neither cell may already be occupied
  const used = new Set();
  for (const p of placements) { used.add(p.cellA); used.add(p.cellB); }
  if (used.has(cellA) || used.has(cellB)) {
    setMsg("Pieces of this domino would overlap an already-placed cell.");
    return;
  }
  dom.used = true;
  placements.push({
    id: dom.id, a: dom.a, b: dom.b,
    cellA, cellB, aR: r, aC: c, bR: r + dr, bC: c + dc,
    orient: orientation,
  });
  selectedDomId = null;
  energyHistory.push({ step: placements.length, energy: computeEnergy() });
  renderAll();
  const e = energyHistory[energyHistory.length - 1].energy;
  const remaining = dominoes.filter((d) => !d.used).length;
  if (remaining === 0 && e === 0) {
    setMsg("🎉 Solved! Every constraint is satisfied. Energy 0.");
  } else if (remaining === 0) {
    setMsg("All dominoes placed, but energy is " + e +
      " — at least one region's values don't satisfy its constraint.");
  } else {
    setMsg(remaining + " domino(es) left. Energy: " + e + ".");
  }
}

document.addEventListener("DOMContentLoaded", () => {
  for (const b of document.querySelectorAll("button.puz")) {
    b.addEventListener("click", () => loadPuzzle(b.dataset.file));
  }
  $("orient-h").addEventListener("click", () => {
    orientation = "H";
    $("orient-h").classList.add("primary");
    $("orient-v").classList.remove("primary");
  });
  $("orient-v").addEventListener("click", () => {
    orientation = "V";
    $("orient-v").classList.add("primary");
    $("orient-h").classList.remove("primary");
  });
  $("undo").addEventListener("click", () => {
    if (!placements.length) return;
    const p = placements.pop();
    dominoes[p.id].used = false;
    energyHistory.push({ step: placements.length, energy: computeEnergy() });
    renderAll();
    setMsg("Undone.");
  });
  $("reset").addEventListener("click", () => {
    placements = [];
    for (const d of dominoes) d.used = false;
    selectedDomId = null;
    resetEnergyHistory();
    renderAll();
    setMsg("Board cleared.");
  });
  $("solve-me").addEventListener("click", async () => {
    // ask Python for the actual solution and play it into placements
    setMsg("Asking the solver …");
    const structure = {
      cells, regions: regions.map((r) => ({
        id: r.id, kind: r.kind, target: r.target, color: r.color,
        n_cells: r.cells.length,
      })),
      dominoes: dominoes.map((d) => ({
        id: d.id, a: d.a, b: d.b, borderline_a: 0, borderline_b: 0,
      })),
    };
    const proxy = solveFn(pyodide.toPy(structure));
    const res = proxy.toJs({ dict_converter: Object.fromEntries });
    proxy.destroy();
    placements = [];
    for (const d of dominoes) d.used = false;
    resetEnergyHistory();
    const all = [];
    for (const cl of res.layout.clusters) for (const p of cl.placements) all.push(p);
    // play each placement back, recomputing the energy chart
    let domIdx = 0;
    for (const p of all) {
      // find a remaining domino matching {va,vb} or {vb,va}
      const found = dominoes.find((d) => !d.used && (
        (d.a === p.va && d.b === p.vb) || (d.a === p.vb && d.b === p.va)));
      if (!found) continue;
      found.used = true;
      const cellA = `${p.a[0]}_${p.a[1]}`, cellB = `${p.b[0]}_${p.b[1]}`;
      placements.push({
        id: found.id,
        a: p.va, b: p.vb,
        cellA, cellB,
        aR: p.a[0], aC: p.a[1], bR: p.b[0], bC: p.b[1],
        orient: p.orient,
      });
      energyHistory.push({ step: placements.length, energy: computeEnergy() });
    }
    renderAll();
    setMsg("Solved by the auto-solver. Energy: 0.");
  });
  boot();
});
