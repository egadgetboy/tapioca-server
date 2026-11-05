"""Isolated DL442 BlurHash groundwork; not wired into library or app responses.

A deterministic 3x4 component BlurHash (28 ASCII chars), using only Python's
standard library. This module must not run while a page is being listed.
Artwork ownership/ACL/version invalidation belong to DL330 and its later
integration; callers MUST NOT expose this preview before that contract exists.
"""

from __future__ import annotations

import math
import subprocess
from typing import Final

_BASE83: Final = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz#$%*+,-.:;=?@[]^_{|}~"
_X: Final = 3
_Y: Final = 4
_FRAME_WIDTH: Final = 16
_FRAME_HEIGHT: Final = 24
_MAX_POSTER_BYTES: Final = 32 * 1024 * 1024


def _base83(number: int, digits: int) -> str:
    return "".join(_BASE83[(number // (83 ** remaining)) % 83] for remaining in range(digits - 1, -1, -1))


def _linear(value: int) -> float:
    c = value / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _srgb(value: float) -> int:
    v = min(1.0, max(0.0, value))
    channel = v * 12.92 if v <= 0.0031308 else 1.055 * v ** (1.0 / 2.4) - 0.055
    return max(0, min(255, int(channel * 255 + 0.5)))


def _quantized_ac(component: float, max_ac: float) -> int:
    scaled = component / max_ac
    rooted = math.copysign(math.sqrt(abs(scaled)), scaled)
    return min(18, max(0, int(rooted * 9 + 9.5)))


def blurhash_rgb24(frame: bytes, width: int, height: int) -> str:
    """Encode one exact-width RGB24 frame to a standard 3x4 BlurHash.

    There are no routes, viewer decisions, caches or external side effects.
    Never call this for unapproved/restricted art; the future storage owner
    is responsible for ACLs before it publishes any generated hash.
    """
    if type(width) is not int or type(height) is not int or width <= 0 or height <= 0:
        raise ValueError("invalid RGB24 frame dimensions")
    if width > 256 or height > 256 or not isinstance(frame, bytes) or len(frame) != 3 * width * height:
        raise ValueError("RGB24 frame has incorrect size")

    linear = [(_linear(frame[i]), _linear(frame[i + 1]), _linear(frame[i + 2]))
              for i in range(0, len(frame), 3)]
    cos_x = [[math.cos(math.pi * x_component * x / width) for x in range(width)]
             for x_component in range(_X)]
    cos_y = [[math.cos(math.pi * y_component * y / height) for y in range(height)]
             for y_component in range(_Y)]
    components: list[tuple[float, float, float]] = []
    pixels = width * height
    for y_component in range(_Y):
        for x_component in range(_X):
            normalization = 1.0 if x_component == 0 and y_component == 0 else 2.0
            red = green = blue = 0.0
            for y in range(height):
                y_basis = cos_y[y_component][y]
                for x in range(width):
                    factor = cos_x[x_component][x] * y_basis
                    r, g, b = linear[y * width + x]
                    red += r * factor
                    green += g * factor
                    blue += b * factor
            norm = normalization / pixels
            components.append((red * norm, green * norm, blue * norm))

    dc = components[0]
    rgb = (_srgb(dc[0]) << 16) | (_srgb(dc[1]) << 8) | _srgb(dc[2])
    ac_components = components[1:]
    strongest = max((abs(channel) for component in ac_components for channel in component), default=0.0)
    quantized_maximum = max(0, min(82, int(strongest * 166 - 0.5)))
    maximum = (quantized_maximum + 1) / 166.0
    parts = [_base83((_X - 1) + 9 * (_Y - 1), 1), _base83(quantized_maximum, 1), _base83(rgb, 4)]
    for red, green, blue in ac_components:
        packed = (_quantized_ac(red, maximum) * 19 + _quantized_ac(green, maximum)) * 19 + _quantized_ac(blue, maximum)
        parts.append(_base83(packed, 2))
    return "".join(parts)


def blurhash_from_image(artwork: bytes) -> str:
    """Decode one in-memory poster through the existing FFmpeg executable.

    A fixed image2pipe input and constrained, scaled RGB24 output avoid file
    paths, shell interpolation, any network protocol, or third-party Python
    package. No viewer-facing or list-time caller exists as of CG-10.
    """
    if not isinstance(artwork, bytes) or not artwork or len(artwork) > _MAX_POSTER_BYTES:
        raise ValueError("invalid poster bytes")
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
        "-protocol_whitelist", "pipe", "-f", "image2pipe", "-i", "pipe:0",
        "-frames:v", "1", "-vf", f"scale={_FRAME_WIDTH}:{_FRAME_HEIGHT}:flags=area",
        "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1",
    ]
    try:
        result = subprocess.run(command, input=artwork, capture_output=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError("ffmpeg could not decode poster") from None
    if result.returncode != 0 or len(result.stdout) != 3 * _FRAME_WIDTH * _FRAME_HEIGHT:
        # Do not include stderr: FFmpeg errors can quote source filenames.
        raise ValueError("ffmpeg could not decode poster")
    return blurhash_rgb24(result.stdout, _FRAME_WIDTH, _FRAME_HEIGHT)
