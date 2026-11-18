import { placeAttachment } from "./attachments.js";

/** Loads an effect folder. A manifest-only effect needs no code; an optional effect.js can override draw(). */
export async function loadEffect(name) {
  const base = `/static/effects/${name}/`;
  const manifest = await (await fetch(base + "manifest.json")).json();
  const images = {};
  for (const a of manifest.attachments || []) {
    const img = new Image();
    img.src = base + a.image;
    await img.decode();
    images[a.image] = img;
  }
  let custom = null;
  if (manifest.script) custom = await import(base + manifest.script); // optional, declared in the manifest
  if (custom && custom.init) await custom.init({ base, manifest });

  return {
    manifest,
    draw(ctx, people, W, H, t) {
      for (const p of people) {
        for (const a of manifest.attachments || []) {
          const pos = placeAttachment(p, a, W, H);
          if (!pos) continue; // missing keypoint: degrade gracefully
          const img = images[a.image];
          const h = pos.width * (img.height / img.width);
          ctx.save();
          ctx.translate(pos.x, pos.y);
          ctx.rotate(pos.angle);
          ctx.drawImage(img, -pos.width / 2, -h, pos.width, h);
          ctx.restore();
        }
      }
      if (custom && custom.draw) custom.draw(ctx, people, W, H, t);
    },
  };
}
