"""Focused synthetic tests for the offline WAV validator."""

from __future__ import annotations

import struct

import pytest

from youtube_automation.audio.wav_validation import parse_wav_file


def _wav(
    data: bytes = b"\x01\x02\x03\x04",
    *,
    channels: int = 1,
    sample_rate: int = 48000,
    bits: int = 16,
    format_tag: int = 1,
    block_align: int | None = None,
    byte_rate: int | None = None,
    chunks: tuple[tuple[bytes, bytes], ...] = (),
    omit_odd_pad: bool = False,
    riff_extent_delta: int = 0,
) -> bytes:
    width = bits // 8
    align = channels * width if block_align is None else block_align
    rate = sample_rate * align if byte_rate is None else byte_rate
    fmt = struct.pack("<HHIIHH", format_tag, channels, sample_rate, rate, align, bits)
    body = bytearray(b"WAVE")
    for chunk_id, payload in ((b"fmt ", fmt), *chunks, (b"data", data)):
        body.extend(chunk_id)
        body.extend(struct.pack("<I", len(payload)))
        body.extend(payload)
        if len(payload) & 1 and not (omit_odd_pad and chunk_id == b"JUNK"):
            body.extend(b"\0")
    return b"RIFF" + struct.pack("<I", len(body) + riff_extent_delta) + body


def test_standard_header_data_offset_and_frame_offsets(tmp_path):
    path = tmp_path / "standard.wav"
    path.write_bytes(_wav(data=b"\0" * 8))
    result = parse_wav_file(path)
    assert result.parseable and result.fully_compliant
    assert result.data_offset == 44
    assert result.frame_to_byte_offset(0) == 44
    assert result.frame_to_byte_offset(1) == 46
    assert result.frame_to_byte_offset(2) == 48


def test_odd_unknown_chunk_is_padded_and_offsets_follow_it(tmp_path):
    path = tmp_path / "padded.wav"
    path.write_bytes(_wav(data=b"\0" * 8, chunks=((b"JUNK", b"abc"),)))
    result = parse_wav_file(path)
    assert result.parseable
    assert result.data_offset == 56
    assert result.frame_to_byte_offset(1) == 58
    assert result.frame_to_byte_offset(2) == 60


def test_missing_odd_chunk_pad_is_rejected(tmp_path):
    path = tmp_path / "no-pad.wav"
    path.write_bytes(_wav(chunks=((b"JUNK", b"abc"),), omit_odd_pad=True))
    result = parse_wav_file(path)
    assert not result.parseable
    assert "chunk data or pad exceeds RIFF extent" in result.errors[0]


def test_riff_extent_must_match_actual_file_size(tmp_path):
    path = tmp_path / "bad-riff-size.wav"
    path.write_bytes(_wav(riff_extent_delta=1))
    result = parse_wav_file(path)
    assert not result.parseable
    assert "RIFF extent" in result.errors[0]


def test_data_must_contain_integral_frames(tmp_path):
    path = tmp_path / "partial-frame.wav"
    path.write_bytes(_wav(data=b"\0\0\0"))
    result = parse_wav_file(path)
    assert not result.parseable
    assert "partial PCM frame" in result.errors[0]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"format_tag": 3}, "only PCM"),
        ({"channels": 0}, "must be positive"),
        ({"sample_rate": 0}, "must be positive"),
        ({"bits": 12}, "bit depth"),
        ({"block_align": 1}, "block alignment"),
    ],
)
def test_invalid_format_parameters_are_rejected(tmp_path, kwargs, message):
    path = tmp_path / "invalid.wav"
    path.write_bytes(_wav(**kwargs))
    result = parse_wav_file(path)
    assert not result.parseable
    assert message in result.errors[0]


def test_byte_rate_mismatch_is_warning_and_parseable(tmp_path):
    path = tmp_path / "byte-rate-mismatch.wav"
    path.write_bytes(_wav(sample_rate=24000, byte_rate=96000))
    result = parse_wav_file(path)
    assert result.parseable
    assert not result.fully_compliant
    assert result.byte_rate == 96000
    assert result.computed_byte_rate == 48000
    assert result.warnings


@pytest.mark.parametrize("frame_index", [-1, 3])
def test_frame_offset_rejects_negative_and_beyond_end_indices(tmp_path, frame_index):
    path = tmp_path / "bounded.wav"
    path.write_bytes(_wav(data=b"\0" * 4))
    result = parse_wav_file(path)
    with pytest.raises(ValueError):
        result.frame_to_byte_offset(frame_index)
