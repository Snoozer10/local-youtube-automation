"""Offline RIFF/WAVE PCM structure and frame-offset validation."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict


class AudioProbe(TypedDict):
    duration: float
    framerate: int
    channels: int
    sampwidth: int
    nframes: int


@dataclass(frozen=True)
class WavValidation:
    """Metadata and diagnostics for one RIFF/WAVE PCM file."""

    file_size: int
    riff_size: int | None
    parseable: bool
    fully_compliant: bool
    channels: int | None = None
    sample_rate: int | None = None
    bits_per_sample: int | None = None
    block_align: int | None = None
    computed_block_align: int | None = None
    byte_rate: int | None = None
    computed_byte_rate: int | None = None
    data_offset: int | None = None
    data_size: int | None = None
    frame_count: int | None = None
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    def frame_to_byte_offset(self, frame_index: int) -> int:
        """Return the byte offset of a frame, allowing the data-end boundary."""
        if not self.parseable or self.data_offset is None or self.frame_count is None:
            raise ValueError("WAV data is not parseable")
        if isinstance(frame_index, bool) or not isinstance(frame_index, int):
            raise TypeError("frame_index must be an integer")
        if frame_index < 0 or frame_index > self.frame_count:
            raise ValueError("frame_index is outside the data chunk")
        assert self.computed_block_align is not None
        return self.data_offset + frame_index * self.computed_block_align


def _invalid(file_size: int, message: str, riff_size: int | None = None) -> WavValidation:
    return WavValidation(file_size, riff_size, False, False, errors=(message,))


def parse_wav_file(path: str | Path) -> WavValidation:
    """Parse and validate a bounded PCM RIFF/WAVE file without changing it."""
    source = Path(path)
    try:
        file_size = source.stat().st_size
        stream = source.open("rb")
    except OSError as exc:
        return _invalid(0, f"cannot open WAV: {exc}")

    with stream:
        if file_size < 12:
            return _invalid(file_size, "file is shorter than the RIFF/WAVE header")
        header = stream.read(12)
        if len(header) != 12 or header[:4] != b"RIFF" or header[8:12] != b"WAVE":
            return _invalid(file_size, "missing RIFF/WAVE header")
        riff_size = struct.unpack_from("<I", header, 4)[0]
        if riff_size + 8 != file_size:
            return _invalid(file_size, "RIFF extent does not match file size", riff_size)

        fmt_values = None
        data_offset = None
        data_size = None
        position = 12
        while position < file_size:
            if file_size - position < 8:
                return _invalid(file_size, "truncated chunk header", riff_size)
            stream.seek(position)
            chunk_header = stream.read(8)
            if len(chunk_header) != 8:
                return _invalid(file_size, "truncated chunk header", riff_size)
            chunk_id = chunk_header[:4]
            chunk_size = struct.unpack_from("<I", chunk_header, 4)[0]
            chunk_data_start = position + 8
            chunk_end = chunk_data_start + chunk_size
            padded_end = chunk_end + (chunk_size & 1)
            if chunk_end > file_size or padded_end > file_size:
                return _invalid(file_size, "chunk data or pad exceeds RIFF extent", riff_size)

            if chunk_id == b"fmt ":
                if fmt_values is not None:
                    return _invalid(file_size, "multiple fmt chunks", riff_size)
                if chunk_size < 16:
                    return _invalid(file_size, "fmt chunk is shorter than 16 bytes", riff_size)
                stream.seek(chunk_data_start)
                fmt = stream.read(16)
                if len(fmt) != 16:
                    return _invalid(file_size, "truncated fmt chunk", riff_size)
                tag, channels, sample_rate, byte_rate, block_align, bits = struct.unpack(
                    "<HHIIHH", fmt
                )
                if tag != 1:
                    return _invalid(file_size, "only PCM format tag 1 is supported", riff_size)
                if channels <= 0 or sample_rate <= 0:
                    return _invalid(file_size, "channels and sample rate must be positive", riff_size)
                if bits not in (8, 16, 24, 32):
                    return _invalid(file_size, "unsupported PCM bit depth", riff_size)
                fmt_values = (channels, sample_rate, byte_rate, block_align, bits)
            elif chunk_id == b"data":
                if fmt_values is None:
                    return _invalid(file_size, "data chunk precedes fmt chunk", riff_size)
                if data_offset is not None:
                    return _invalid(file_size, "multiple data chunks", riff_size)
                data_offset = chunk_data_start
                data_size = chunk_size

            position = padded_end

        if position != file_size:
            return _invalid(file_size, "chunks do not end at RIFF extent", riff_size)
        if fmt_values is None:
            return _invalid(file_size, "missing fmt chunk", riff_size)
        if data_offset is None or data_size is None:
            return _invalid(file_size, "missing data chunk", riff_size)

    channels, sample_rate, byte_rate, block_align, bits = fmt_values
    computed_align = channels * (bits // 8)
    computed_rate = sample_rate * computed_align
    if block_align != computed_align:
        return WavValidation(
            file_size, riff_size, False, False, channels, sample_rate, bits,
            block_align, computed_align, byte_rate, computed_rate, data_offset,
            data_size, None, (), ("declared block alignment does not match PCM format",),
        )
    if data_size % computed_align:
        return WavValidation(
            file_size, riff_size, False, False, channels, sample_rate, bits,
            block_align, computed_align, byte_rate, computed_rate, data_offset,
            data_size, None, (), ("data size contains a partial PCM frame",),
        )

    warnings: tuple[str, ...] = ()
    if byte_rate != computed_rate:
        warnings = (f"declared byte rate {byte_rate} differs from computed {computed_rate}",)
    return WavValidation(
        file_size=file_size, riff_size=riff_size, parseable=True,
        fully_compliant=not warnings, channels=channels, sample_rate=sample_rate,
        bits_per_sample=bits, block_align=block_align,
        computed_block_align=computed_align, byte_rate=byte_rate,
        computed_byte_rate=computed_rate, data_offset=data_offset,
        data_size=data_size, frame_count=data_size // computed_align, warnings=warnings,
    )
