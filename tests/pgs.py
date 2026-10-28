"""Blu-ray picture subtitles (PGS) for tests, made by hand (ffmpeg can't make
picture subtitles from text): a .sup stream with white bars shown at the
times given, for a canvas of the size given. FFmpeg learns a PGS track's
size only from a subtitle in about its first five seconds; a later first
one leaves the canvas at the film's size until it comes."""

from __future__ import annotations

import struct
from pathlib import Path


def _segment(kind: int, body: bytes, seconds: float) -> bytes:
    t = round(seconds * 90000)
    return b"PG" + struct.pack(">IIBH", t, t, kind, len(body)) + body


def _bar(width: int, height: int) -> bytes:
    """`height` lines of `width` pixels of palette entry 1 (white)."""
    line = bytes([0x00, 0xC0 | (width >> 8), width & 0xFF, 0x01]) + b"\x00\x00"
    return line * height


def write(
    path: Path, canvas: tuple[int, int], cues: list[tuple[float, float, tuple[int, int, int, int]]]
) -> Path:
    """`cues`: (start, end, (x, y, width, height)) each, one bar shown from
    `start` to `end` seconds on a `canvas` (width, height)."""
    w, h = canvas
    out = b""
    n = 0
    for start, end, (x, y, bw, bh) in cues:
        window = bytes([1]) + struct.pack(">BHHHH", 0, x, y, bw, bh)
        shown = struct.pack(">HHBHBBBB", w, h, 0x10, n, 0x80, 0, 0, 1) + struct.pack(
            ">HBBHH", 0, 0, 0, x, y
        )
        palette = bytes([0, 0]) + bytes([1, 235, 128, 128, 255])
        data = _bar(bw, bh)
        picture = (
            struct.pack(">HBB", 0, 0, 0xC0)
            + (len(data) + 4).to_bytes(3, "big")
            + struct.pack(">HH", bw, bh)
            + data
        )
        out += (
            _segment(0x16, shown, start)
            + _segment(0x17, window, start)
            + _segment(0x14, palette, start)
        )
        out += _segment(0x15, picture, start) + _segment(0x80, b"", start)
        n += 1
        cleared = struct.pack(">HHBHBBBB", w, h, 0x10, n, 0x00, 0, 0, 0)
        out += _segment(0x16, cleared, end) + _segment(0x17, window, end) + _segment(0x80, b"", end)
        n += 1
    path.write_bytes(out)
    return path
