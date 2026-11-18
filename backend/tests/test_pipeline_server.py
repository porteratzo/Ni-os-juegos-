import time

import numpy as np
from fastapi.testclient import TestClient

from kidsar.capture.base import Frame
from kidsar.config import Settings
from kidsar.pipeline import Pipeline
from kidsar.protocol import decode_message
from kidsar.server import create_app
from kidsar.vision.fake_pose import FakePose


class ScriptedSource:
    """Hands out queued frames once each; used to test stale/offline behaviour."""
    def __init__(self, frames):
        self.frames = list(frames)
    def start(self): pass
    def stop(self): pass
    def latest(self):
        return self.frames.pop(0) if self.frames else None


def _img():
    return np.zeros((36, 64, 3), np.uint8)


def test_stream_delivers_frames_with_people():
    app = create_app(Settings(width=320, height=180, fps=30))
    with TestClient(app) as c:
        assert c.get("/health").json()["ok"]
        with c.websocket_connect("/ws/stream") as ws:
            header, jpeg = decode_message(ws.receive_bytes())
            assert jpeg[:2] == b"\xff\xd8"
            assert header.width == 320 and len(header.people) == 2
            h2, _ = decode_message(ws.receive_bytes())
            assert h2.frame_id > header.frame_id
        m = c.get("/metrics").json()
        assert m["frames"] > 0 and m["timing_ms"] is not None


def test_consumer_only_gets_newest_frame():
    frames = [Frame(_img(), int(time.time() * 1000)) for _ in range(5)]
    p = Pipeline(ScriptedSource(frames), FakePose(1))
    p.start()
    time.sleep(0.3)  # let all five be processed while nobody consumes
    item = p.wait_newer(0, timeout=1)
    p.stop()
    assert item is not None and item[0] == 5  # skipped 1-4: no backlog


def test_offline_frame_flagged():
    p = Pipeline(ScriptedSource([Frame(_img(), 0, offline=True)]), FakePose(1))
    p.start()
    item = p.wait_newer(0, timeout=1)
    p.stop()
    header, jpeg = decode_message(item[1])
    assert header.camera_offline and jpeg == b"" and header.people == []


def test_silence_becomes_offline_message():
    p = Pipeline(ScriptedSource([]), FakePose(1), stale_after_s=0.1)
    p.start()
    item = p.wait_newer(0, timeout=1)
    p.stop()
    assert item is not None and decode_message(item[1])[0].camera_offline
