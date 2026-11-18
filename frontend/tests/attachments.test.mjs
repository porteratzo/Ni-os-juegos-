// Run: node --test frontend/tests/attachments.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { placeAttachment } from "../shared/attachments.js";
import { K } from "../shared/keypoints.js";

const att = { anchor: "head", width_per_head: 2.4, offset_x: 0, offset_y: -0.35, rotate_with: "shoulders" };
const W = 1280, H = 720;
const blank = () => Array.from({ length: 17 }, () => ({ x: 0, y: 0, c: 0 }));
function person({ mirror = false } = {}) {
  const kp = blank(); const fx = (x) => (mirror ? 1 - x : x);
  const set = (i, x, y) => (kp[i] = { x: fx(x), y, c: 0.9 });
  set(K.NOSE, 0.5, 0.2); set(K.LEFT_EAR, 0.47, 0.2); set(K.RIGHT_EAR, 0.53, 0.2);
  set(K.LEFT_SHOULDER, 0.4, 0.4); set(K.RIGHT_SHOULDER, 0.6, 0.4);
  return { keypoints: kp };
}

test("places cap above the head, sized from ear distance", () => {
  const r = placeAttachment(person(), att, W, H);
  assert.ok(Math.abs(r.width - 2.4 * 0.06 * W) < 1);
  assert.ok(r.y < 0.2 * H);
  assert.ok(Math.abs(r.angle) < 1e-6);
});

test("mirrored view does not flip the cap upside down", () => {
  const r = placeAttachment(person({ mirror: true }), att, W, H);
  assert.ok(Math.abs(r.angle) < 0.01, `angle was ${r.angle}`);
});

test("tilted shoulders rotate the cap", () => {
  const p = person(); p.keypoints[K.RIGHT_SHOULDER].y = 0.45;
  assert.ok(placeAttachment(p, att, W, H).angle > 0.1);
});

test("missing keypoints degrade to null instead of throwing", () => {
  assert.equal(placeAttachment({ keypoints: blank() }, att, W, H), null);
  const p = person(); p.keypoints[K.NOSE].c = 0; p.keypoints[K.LEFT_EYE].c = 0; p.keypoints[K.RIGHT_EYE].c = 0;
  assert.equal(placeAttachment(p, att, W, H), null);
});
