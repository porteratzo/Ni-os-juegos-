# Ni-os-juegos-

AR party game for kids. Architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Status: M0 skeleton (no camera, no Redis, runs anywhere)

A synthetic camera and two fake walking skeletons stream through the real pipeline and WebSocket
protocol to a display page that draws a cap on each head.

```bash
cd backend && pip install -e '.[dev]'
python -m kidsar.server            # http://127.0.0.1:8000/   (add ?debug for fps/latency/skeleton)
python -m pytest                   # backend tests
node --test frontend/tests/attachments.test.mjs   # frontend geometry tests
python scripts/make_placeholder_art.py            # regenerate placeholder costume art
```

Settings are env vars (`KIDSAR_PORT`, `KIDSAR_FPS`, `KIDSAR_WIDTH`, ...); see `backend/kidsar/config.py`.
The server binds to 127.0.0.1 by default. The camera link (`my_depthai` over Redis) arrives in M1a;
the Redis message format is isolated in `backend/kidsar/capture/camera_stream_codec.py` (placeholder
until the shared library is decoupled).
