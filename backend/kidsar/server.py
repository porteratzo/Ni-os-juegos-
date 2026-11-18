"""FastAPI app: serves the display page and the /ws/stream feed."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .capture.synthetic import SyntheticCamera
from .config import Settings
from .pipeline import Pipeline
from .vision.fake_pose import FakePose

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def build_pipeline(s: Settings) -> Pipeline:
    if s.source == "synthetic":
        source = SyntheticCamera(s.width, s.height, s.fps)
    else:
        raise RuntimeError(f"source {s.source!r} is not implemented yet (redis arrives in M1a)")
    return Pipeline(source, FakePose(n_people=2), s.jpeg_quality, s.stale_after_s)


def create_app(settings: Optional[Settings] = None, pipeline: Optional[Pipeline] = None) -> FastAPI:
    s = settings or Settings.from_env()
    pipe = pipeline or build_pipeline(s)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        pipe.start()
        try:
            yield
        finally:
            pipe.stop()

    app = FastAPI(title="kidsar", lifespan=lifespan)

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "camera_offline": pipe.metrics.camera_offline}

    @app.get("/metrics")
    def metrics() -> JSONResponse:
        m = pipe.metrics
        return JSONResponse({"frames": m.frames, "fps": round(m.fps, 1),
                             "timing_ms": m.last_timing_ms, "camera_offline": m.camera_offline})

    @app.websocket("/ws/stream")
    async def stream(ws: WebSocket) -> None:
        await ws.accept()
        last_id = 0
        loop = asyncio.get_running_loop()
        try:
            while True:
                item = await loop.run_in_executor(None, pipe.wait_newer, last_id, 1.0)
                if item is None:
                    continue
                last_id, msg = item
                await ws.send_bytes(msg)
        except (WebSocketDisconnect, RuntimeError):
            return

    @app.get("/")
    def display() -> FileResponse:
        return FileResponse(FRONTEND / "display" / "index.html")

    if FRONTEND.exists():
        app.mount("/static", StaticFiles(directory=FRONTEND), name="static")
    return app


def main() -> None:
    import uvicorn

    s = Settings.from_env()
    uvicorn.run(create_app(s), host=s.host, port=s.port, log_level="info")


if __name__ == "__main__":
    main()
