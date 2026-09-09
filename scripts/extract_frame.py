#!/usr/bin/env python3
"""Extract a single frame from the Pokemon All-Stars 1025 video at a given
timestamp, without downloading the whole video.

Resolves a direct stream URL with yt-dlp (needs deno on PATH for the YouTube
JS challenge) and seeks with ffmpeg.

Usage:
    python3 extract_frame.py 90.5 samples/raw/t90.jpg
    python3 extract_frame.py 00:01:30 samples/raw/t90.jpg --height 720
"""

import argparse
import os
import subprocess
import sys

VIDEO_URL = "https://www.youtube.com/watch?v=PqOBtBOsB_I"
YT_DLP = os.path.expanduser("~/workspace/yt-venv/bin/yt-dlp")


def parse_ts(s: str) -> float:
    if ":" in s:
        parts = [float(p) for p in s.split(":")]
        t = 0.0
        for p in parts:
            t = t * 60 + p
        return t
    return float(s)


def stream_url(height: int | None) -> str:
    env = dict(os.environ)
    env["PATH"] = os.path.expanduser("~/.deno/bin") + os.pathsep + env["PATH"]
    # Prefer direct HTTPS streams; exclude HLS manifests (they 403 in ffmpeg).
    fmt = ("bv*[protocol^=https]/b[protocol^=https]" if height is None
           else f"bv*[height<={height}][protocol^=https]/b[height<={height}][protocol^=https]")
    out = subprocess.run(
        [YT_DLP, "-g", "-f", fmt, VIDEO_URL],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    # first line is the video-only (or progressive) stream
    return out.stdout.strip().splitlines()[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("timestamp", help="seconds or HH:MM:SS")
    ap.add_argument("output", help="output image path")
    ap.add_argument("--height", type=int, default=None,
                    help="cap video height (default: best available resolution)")
    ap.add_argument("--quality", type=int, default=2, help="ffmpeg -q:v (2=high)")
    args = ap.parse_args()

    t = parse_ts(args.timestamp)
    url = stream_url(args.height)
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-ss", str(t),
            "-i", url,
            "-frames:v", "1",
            "-q:v", str(args.quality),
            args.output,
        ],
        check=True,
    )
    print(f"saved {args.output} @ t={t:.2f}s")


if __name__ == "__main__":
    main()
