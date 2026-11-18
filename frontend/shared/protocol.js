// Decodes [4-byte BE header length][JSON header][JPEG bytes] (see backend/kidsar/protocol.py).
export const PROTOCOL_VERSION = 1;

export function decodeMessage(buf) {
  const view = new DataView(buf);
  const n = view.getUint32(0, false);
  const header = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, 4, n)));
  if (header.v !== PROTOCOL_VERSION) throw new Error(`unsupported protocol version ${header.v}`);
  const jpeg = new Uint8Array(buf, 4 + n);
  return { header, jpeg };
}
