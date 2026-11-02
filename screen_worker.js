// Web Worker: runs the SGP4 close-approach screening off the UI thread.
try { importScripts('vendor/satellite.min.js'); } catch (e) { importScripts('https://cdn.jsdelivr.net/npm/satellite.js@5.0.0/dist/satellite.min.js'); }
importScripts('astra_core.js');
onmessage = ev => {
  const d = ev.data;
  try {
    const res = ASTRA.screen(satellite, d.p, d.c, d.t0, d.hours, d.step, d.thr, p => postMessage({ progress: p }));
    postMessage({ res });
  } catch (e) { postMessage({ error: String(e && e.message || e) }); }
};
