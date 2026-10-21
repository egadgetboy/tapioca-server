"""(Temporary, for 1.42.0's arm64 and amd64 failures: the floor test's whole table in the image, and
how the worst ones measure other ways. Removed before the release.)"""

import json
import re
import subprocess
import tempfile
from pathlib import Path

from app import pictures
from tests.test_pictures import planes_ssim

HERE = Path("tests/pictures")


def ff(args, data=None):
    return subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", *args], input=data,
                          capture_output=True, check=True).stdout


def props(data):
    with tempfile.NamedTemporaryFile() as f:
        f.write(data)
        f.flush()
        out = subprocess.run(["ffprobe", "-v", "error", "-show_frames", "-show_streams", "-of", "json", f.name],
                             capture_output=True, check=True).stdout
    said = json.loads(out)
    keep = ("codec_name", "pix_fmt", "color_range", "color_space", "chroma_location", "width", "height")
    return {k: (said["frames"][0] | said["streams"][0]).get(k) for k in keep}


def ssim_other(made, lossless, pix, extra):
    with tempfile.TemporaryDirectory() as d:
        Path(d, "m").write_bytes(made)
        Path(d, "l.y4m").write_bytes(lossless)
        said = subprocess.run(["ffmpeg", "-hide_banner", *extra, "-i", f"{d}/m", "-i", f"{d}/l.y4m", "-lavfi",
                               f"[0:v]format={pix}[x];[1:v]format={pix}[y];[x][y]ssim", "-f", "null", "-"],
                              capture_output=True, check=True).stderr.decode()
    return [round(float(x), 4) for x in re.search(r"SSIM Y:([\d.]+).*U:([\d.]+).*V:([\d.]+)", said).groups()]


worst = []
for kind in ("poster", "backdrop"):
    for n, v in enumerate("ab"):
        source = (HERE / f"{kind}-{v}.jpg").read_bytes()
        for width in pictures.widths(kind):
            height = pictures.height_for(kind, width)
            for fmt, pix in (("jpeg", "yuvj420p"), ("webp", "yuv420p")):
                lossless = ff(["-i", "pipe:0", "-frames:v", "1", "-vf",
                               f"scale='min({width},iw)':'min({height},ih)':force_original_aspect_ratio=decrease,format={pix}",
                               "-f", "yuv4mpegpipe", "-strict", "-1", "pipe:1"], source)
                made = ff(["-f", "yuv4mpegpipe", "-i", "pipe:0", "-frames:v", "1",
                           *pictures.encoder_args(kind, width, fmt), "pipe:1"], lossless)
                got = [round(x, 4) for x in planes_ssim(made, lossless, pix)]
                print(kind, v, width, fmt, got, len(made), flush=True)
                if min(got) < 0.985:
                    worst.append((kind, v, width, fmt, pix, lossless, made, got))

for kind, v, width, fmt, pix, lossless, made, got in worst[:6]:
    print("==", kind, v, width, fmt, got)
    print("   y4m header:", lossless[:100])
    print("   made:", props(made))
    print("   one thread:", ssim_other(made, lossless, pix, ["-threads", "1", "-filter_threads", "1"]))
    # (The made picture decoded to y4m by the same FFmpeg first, then measured y4m to y4m.)
    back = ff(["-i", "pipe:0", "-frames:v", "1", "-vf", f"format={pix}", "-f", "yuv4mpegpipe", "-strict", "-1", "pipe:1"], made)
    print("   made as y4m header:", back[:100])
    print("   y4m to y4m:", ssim_other(back, lossless, pix, []))
    # (Made again, the same way: is it the same bytes?)
    again = ff(["-f", "yuv4mpegpipe", "-i", "pipe:0", "-frames:v", "1", *pictures.encoder_args(kind, width, fmt), "pipe:1"], lossless)
    print("   made again identical:", again == made)
