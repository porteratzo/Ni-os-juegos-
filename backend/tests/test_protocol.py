import pytest

from kidsar.protocol import (KEYPOINT_NAMES, FrameHeader, Keypoint, Person, decode_message,
                             encode_message)
from kidsar.vision.fake_pose import FakePose
import numpy as np


def test_round_trip():
    people = FakePose(2).estimate(np.zeros((4, 4, 3), np.uint8), 1.0)
    h = FrameHeader(7, 1731880000123, 1280, 720, people=people, timing_ms={"pose": 1.234})
    out, jpeg = decode_message(encode_message(h, b"\xff\xd8jpegbytes"))
    assert jpeg == b"\xff\xd8jpegbytes"
    assert out.frame_id == 7 and out.width == 1280 and len(out.people) == 2
    assert len(out.people[0].keypoints) == len(KEYPOINT_NAMES) == 17
    assert out.timing_ms["pose"] == 1.23


def test_rejects_bad_version_and_truncation():
    good = encode_message(FrameHeader(1, 0, 1, 1), b"")
    with pytest.raises(ValueError):
        decode_message(good[:6])
    with pytest.raises(ValueError):
        decode_message(b"\x00")
    bad = good.replace(b'"v":1', b'"v":99')
    # length prefix is unchanged because the replacement has the same length
    with pytest.raises(ValueError):
        decode_message(bad)


def test_offline_flag_survives():
    out, _ = decode_message(encode_message(FrameHeader(1, 0, 0, 0, camera_offline=True), b""))
    assert out.camera_offline
