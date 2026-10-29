// Record twin3d.html in headless Chrome via CDP: node rec.mjs <outdir> <preset> <seconds> [w] [h]
import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";

const [out, preset = "rpmctl", secs = "14", W = "1280", H = "800"] = process.argv.slice(2);
mkdirSync(out, { recursive: true });
const chrome = spawn("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", [
  "--headless=new", "--remote-debugging-port=9333", "--user-data-dir=" + out + "/../profile",
  `--window-size=${W},${H}`, "--use-angle=metal", "--enable-webgl", "--ignore-gpu-blocklist",
  "--hide-scrollbars", "about:blank"], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let ws;
for (let i = 0; i < 50; i++) {
  try {
    const list = await (await fetch("http://127.0.0.1:9333/json")).json();
    const page = list.find((t) => t.type === "page");
    if (page) { ws = new WebSocket(page.webSocketDebuggerUrl); break; }
  } catch {}
  await sleep(200);
}
await new Promise((r) => ws.addEventListener("open", r));
let id = 0; const pending = new Map();
ws.addEventListener("message", (e) => { const m = JSON.parse(e.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } });
const send = (method, params = {}) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const ev = async (expr) => (await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true })).result?.result?.value;

await send("Emulation.setDeviceMetricsOverride", { width: +W, height: +H, deviceScaleFactor: 1, mobile: false });
await send("Page.navigate", { url: "http://127.0.0.1:8766/twin3d.html" });
for (let i = 0; i < 100; i++) { if (await ev("document.readyState==='complete' && (getComputedStyle(document.getElementById('loading')).display==='none' || document.getElementById('loading').hidden)")) break; await sleep(200); }
await sleep(1500);
console.log("webgl:", await ev("!!document.getElementById('view').getContext('webgl2')||'?'"));
await ev(`document.querySelector('[data-preset="${preset}"]').click()`);
const t0 = Date.now(); let n = 0;
while (Date.now() - t0 < +secs * 1000) {
  const r = await send("Page.captureScreenshot", { format: "png" });
  writeFileSync(`${out}/f${String(n++).padStart(4, "0")}.png`, Buffer.from(r.result.data, "base64"));
  writeFileSync(`${out}/times.txt`, `${n} ${Date.now() - t0}\n`, { flag: "a" });
}
console.log("frames", n, "in", Date.now() - t0, "ms");
ws.close(); chrome.kill();
