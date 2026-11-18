import { decodeMessage } from "/static/shared/protocol.js";
import { loadEffect } from "/static/shared/effects.js";
import { SKELETON, MIN_CONF } from "/static/shared/keypoints.js";

const params = new URLSearchParams(location.search);
const MIRROR = params.get("mirror") !== "0";
const DEBUG = params.has("debug");
const EFFECT = params.get("effect") || "mario-cap";

const canvas = document.getElementById("c");
const ctx = canvas.getContext("2d");
const statusEl = document.getElementById("status");
const hud = document.getElementById("hud");
if (DEBUG) hud.style.display = "block";

let effect = null;
let latest = null; // newest decoded {bitmap, header}; rendering always uses the newest only
let lastRender = 0;
let fpsCount = 0, fpsT = performance.now(), fps = 0;
let lastMsgAt = 0;

loadEffect(EFFECT).then((e) => (effect = e)).catch((e) => console.error("effect load failed", e));

function connect() {
  const ws = new WebSocket(`ws://${location.host}/ws/stream`);
  ws.binaryType = "arraybuffer";
  ws.onmessage = async (ev) => {
    const { header, jpeg } = decodeMessage(ev.data);
    lastMsgAt = performance.now();
    if (header.camera_offline) { latest = { offline: true, header }; return; }
    const bitmap = await createImageBitmap(new Blob([jpeg], { type: "image/jpeg" }));
    if (latest && latest.bitmap) latest.bitmap.close();
    latest = { bitmap, header, receivedAt: performance.now() };
  };
  ws.onclose = () => { latest = null; setTimeout(connect, 1000); };
  ws.onerror = () => ws.close();
}
connect();

function draw(now) {
  requestAnimationFrame(draw);
  const offline = !latest || latest.offline || now - lastMsgAt > 1500;
  statusEl.style.display = offline ? "flex" : "none";
  if (offline || latest.header === lastRender) return;
  lastRender = latest.header;
  const { bitmap, header } = latest;
  const W = canvas.width = header.width, H = canvas.height = header.height;

  ctx.save();
  if (MIRROR) { ctx.translate(W, 0); ctx.scale(-1, 1); }
  ctx.drawImage(bitmap, 0, 0, W, H);
  ctx.restore();

  // Mirror keypoints by flipping x so effects (and any text) stay un-reversed.
  const people = header.people.map((p) => ({
    ...p,
    keypoints: p.keypoints.map((k) => ({ ...k, x: MIRROR ? 1 - k.x : k.x })),
  }));
  if (effect) effect.draw(ctx, people, W, H, now / 1000);

  if (DEBUG) {
    ctx.lineWidth = 3; ctx.strokeStyle = "#0f0";
    for (const p of people) for (const [a, b] of SKELETON) {
      const A = p.keypoints[a], B = p.keypoints[b];
      if (A.c < MIN_CONF || B.c < MIN_CONF) continue;
      ctx.beginPath(); ctx.moveTo(A.x * W, A.y * H); ctx.lineTo(B.x * W, B.y * H); ctx.stroke();
    }
    fpsCount++;
    if (now - fpsT > 1000) { fps = fpsCount * 1000 / (now - fpsT); fpsCount = 0; fpsT = now; }
    const age = Date.now() - header.t_capture_ms;
    hud.textContent = `fps ${fps.toFixed(0)}  age ${age} ms  people ${people.length}\n` +
      Object.entries(header.timing_ms).map(([k, v]) => `${k} ${v}`).join("  ");
  }
}
requestAnimationFrame(draw);
