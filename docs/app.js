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

async function loadFromFetch(path) {
  setStatus("Fetching " + path + " …");
  const buf = await (await fetch(path)).arrayBuffer();
  return new Uint8Array(buf);
}

for (const btn of document.querySelectorAll("button.puz")) {
  btn.addEventListener("click", async () => {
    try {
      const u8 = await loadFromFetch("puzzles/" + btn.dataset.puz +
        "-example.png");
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
