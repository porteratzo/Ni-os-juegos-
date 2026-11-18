import base64
import json
from pathlib import Path

import pytest

from kidsar.capture import camera_stream_codec as codec

FIX = json.loads((Path(__file__).parent / "fixtures" / "camera_message.json").read_text())


def _fields(**over):
    f = {k.encode(): v.encode() for k, v in FIX["fields"].items()}
    f[b"data"] = base64.b64decode(FIX["data_b64"])
    for k, v in over.items():
        if v is None:
            f.pop(k.encode(), None)
        else:
            f[k.encode()] = v if isinstance(v, bytes) else v.encode()
    return f


def test_decode_fixture():
    m = codec.decode(_fields())
    assert (m.camera_id, m.output_type, m.width, m.height) == ("camera_1", "preview", 64, 36)
    assert m.jpeg[:2] == b"\xff\xd8" and not m.is_fallback
    assert m.t_capture is None  # not published yet (F4)
    assert m.t_publish.year == 2026


def test_fallback_flag():
    assert codec.decode(_fields(is_fallback="true")).is_fallback


def test_capture_timestamp_used_when_present():
    m = codec.decode(_fields(t_capture="2026-01-22T12:34:56.700000"))
    assert m.t_capture is not None and m.t_capture < m.t_publish


@pytest.mark.parametrize("missing", ["camera_id", "output_type", "data", "timestamp"])
def test_missing_field_rejected(missing):
    with pytest.raises(ValueError):
        codec.decode(_fields(**{missing: None}))


def test_non_jpeg_rejected():
    with pytest.raises(ValueError):
        codec.decode(_fields(format="png"))
