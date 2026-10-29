// node turn.mjs <url> <outdir> <nframes> <w> <h>  — deterministic turntable via window.setAngle
import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
const [url, out, N = "72", W = "720", H = "540"] = process.argv.slice(2);
mkdirSync(out, { recursive: true });
const chrome = spawn("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", ["--headless=new", "--remote-debugging-port=9334",
  "--user-data-dir=" + out + "/../profile2", `--window-size=${W},${H}`, "--use-angle=metal", "--ignore-gpu-blocklist", "--hide-scrollbars", "about:blank"], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let ws;
for (let i = 0; i < 50 && !ws; i++) { try { const p = (await (await fetch("http://127.0.0.1:9334/json")).json()).find((t) => t.type === "page" && t.url === "about:blank"); if (p) ws = new WebSocket(p.webSocketDebuggerUrl); } catch {} await sleep(200); }
if (ws.readyState !== 1) await new Promise((r) => ws.addEventListener("open", r));
let id = 0; const pend = new Map();
ws.addEventListener("message", (e) => { const m = JSON.parse(e.data); if (pend.has(m.id)) { pend.get(m.id)(m); pend.delete(m.id); } });
const send = (method, params = {}) => new Promise((r) => { const i = ++id; pend.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const ev = async (x) => (await send("Runtime.evaluate", { expression: x, awaitPromise: true, returnByValue: true })).result?.result?.value;
await send("Emulation.setDeviceMetricsOverride", { width: +W, height: +H, deviceScaleFactor: 1, mobile: false });
await send("Page.navigate", { url });
for (let i = 0; i < 150 && !(await ev("document.readyState==='complete' && getComputedStyle(document.getElementById('loading')).display==='none'")); i++) await sleep(200);
await sleep(1500);
await ev(`document.getElementById('cmd').value='dcm:speed 255'; document.getElementById('cform').requestSubmit();`);
await ev("document.querySelector('.viewbar').style.display='none'"); await sleep(2500);
const rect = await ev("(()=>{const r=document.getElementById('view').getBoundingClientRect();return [r.x,r.y,r.width,r.height]})()");
const a0 = Math.atan2(225, -230);
for (let k = 0; k < +N; k++) {
  const a = a0 + (2 * Math.PI * k) / +N;
  await ev(`camera.position.set(20+330*Math.cos(${a}),190,25+330*Math.sin(${a})); controls.target.set(20,55,25); controls.update();`);
  await sleep(70);
  const r = await send("Page.captureScreenshot", { format: "png", clip: { x: rect[0], y: rect[1], width: rect[2], height: rect[3], scale: 1 } });
  writeFileSync(`${out}/f${String(k).padStart(4, "0")}.png`, Buffer.from(r.result.data, "base64"));
}
if (process.env.PROBE) console.log("probe", JSON.stringify(await ev(`probe(${process.env.PROBE})`)));
console.log("frames", N); ws.close(); chrome.kill();
