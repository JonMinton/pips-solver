"use strict";

const $ = (id) => document.getElementById(id);
const statusEl = $("status");
const setStatus = (m) => { statusEl.textContent = m; };

$("date").textContent = new Date().toLocaleDateString(undefined, {
  weekday: "long", year: "numeric", month: "long", day: "numeric",
});

let pyodide = null;
let runFn = null;     // Python pips.webapi.run, as a callable PyProxy
let busy = false;

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

    setStatus("Ready. Pick Easy / Medium / Hard, upload a screenshot, "
      + "or paste an image URL.");
    for (const el of document.querySelectorAll("button,#file,#url"))
      el.disabled = false;
  } catch (e) {
    setStatus("Failed to start: " + e + " (try reloading).");
    console.error(e);
  }
}

async function solveBytes(u8, previewBlobType) {
  if (!runFn || busy) return;
  busy = true;
  $("badges").classList.add("hidden");
  try {
    const url = URL.createObjectURL(new Blob([u8], {
      type: previewBlobType || "image/png",
    }));
    $("preview").src = url;

    setStatus("Parsing the screenshot and solving…");
    $("parsed").textContent = "…";
    $("solution").textContent = "…";

    pyodide.FS.writeFile("/tmp/in.png", u8);
    // run() is synchronous CPU work; yield first so the UI repaints
    await new Promise((r) => setTimeout(r, 30));

    const proxy = runFn();
    const res = proxy.toJs({ dict_converter: Object.fromEntries });
    proxy.destroy();

    $("parsed").textContent = res.parsed;
    $("solution").textContent = res.solution;
    try {
      $("svgwrap").innerHTML = buildSVG(res.layout);
      $("lh").textContent = res.layout.n_h;
      $("lv").textContent = res.layout.n_v;
      $("legend").classList.remove("hidden");
    } catch (e) {
      $("svgwrap").innerHTML =
        '<p class="muted">(graphical view unavailable)</p>';
      console.error(e);
    }
    $("b-parse").textContent = "parse " + res.parse_ms + " ms";
    $("b-solve").textContent = "solve " + res.solve_ms + " ms";
    $("b-grid").textContent =
      res.n_cells + " cells · " + res.n_dominoes + " dominoes · " +
      res.n_regions + " regions · " + res.n_clusters + " cluster(s)";
    const v = $("b-verified");
    if (res.solved && res.verified) {
      v.textContent = "solution verified ✓"; v.className = "badge ok";
    } else {
      v.textContent = res.solved ? "solved (unverified)" : "no solution";
      v.className = "badge";
    }
    $("badges").classList.remove("hidden");
    setStatus("Done.");
  } catch (e) {
    setStatus("Error: " + e);
    $("solution").textContent = String(e);
    console.error(e);
  } finally {
    busy = false;
  }
}

function buildSVG(layout) {
  const CS = 46, INS = 5, PAD = 14, GY = 26;
  const H_COL = "#2f6f9f", V_COL = "#c8762a";
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
