// Declarative effect: attach an image to a body anchor. Pure geometry, unit-testable in Node.
import { K, MIN_CONF } from "./keypoints.js";

const ok = (p) => p && p.c >= MIN_CONF;

/** Where to put an attachment for one person, in pixel space. Returns null if keypoints are missing. */
export function placeAttachment(person, att, W, H) {
  const kp = person.keypoints;
  if (att.anchor !== "head") return null; // other anchors arrive with M2
  const eyes = [kp[K.LEFT_EYE], kp[K.RIGHT_EYE]].filter(ok);
  const ears = [kp[K.LEFT_EAR], kp[K.RIGHT_EAR]].filter(ok);
  const nose = ok(kp[K.NOSE]) ? kp[K.NOSE] : null;
  const center = nose || (eyes.length ? eyes[0] : null);
  if (!center) return null;

  // Head size: ear-to-ear, else eye-to-eye * 2, else shoulder width * 0.5.
  let head = 0;
  if (ears.length === 2) head = Math.hypot((ears[0].x - ears[1].x) * W, (ears[0].y - ears[1].y) * H);
  else if (eyes.length === 2) head = 2 * Math.hypot((eyes[0].x - eyes[1].x) * W, (eyes[0].y - eyes[1].y) * H);
  else if (ok(kp[K.LEFT_SHOULDER]) && ok(kp[K.RIGHT_SHOULDER]))
    head = 0.5 * Math.hypot((kp[K.LEFT_SHOULDER].x - kp[K.RIGHT_SHOULDER].x) * W,
                            (kp[K.LEFT_SHOULDER].y - kp[K.RIGHT_SHOULDER].y) * H);
  if (head <= 1) return null;

  let angle = 0;
  const l = kp[K.LEFT_SHOULDER], r = kp[K.RIGHT_SHOULDER];
  if (att.rotate_with === "shoulders" && ok(l) && ok(r)) {
    // Order left-to-right ON SCREEN so a mirrored view (x flipped) still gives a small tilt, not ~180 deg.
    const [a, b] = l.x <= r.x ? [l, r] : [r, l];
    angle = Math.atan2((b.y - a.y) * H, (b.x - a.x) * W);
  }

  const width = head * att.width_per_head;
  return {
    x: center.x * W + (att.offset_x || 0) * head,
    y: center.y * H + (att.offset_y || 0) * head * 2,
    width,
    angle,
  };
}
