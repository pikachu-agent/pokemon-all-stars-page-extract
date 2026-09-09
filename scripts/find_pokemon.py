#!/usr/bin/env python3
"""Find a Pokemon's illustrated page in the All-Stars 1025 video.

Pass an English, romaji, or Japanese name. The script resolves it to its
position in the song order (lyrics.txt / names.json) and estimates a
timestamp by interpolating between anchor points: hand-verified samples
(samples/samples.json) plus auto anchors from exact lyric-name hits in the
18 subtitle blocks (blocks.json).

It reports which subtitle block the estimate falls in (or between), and can
extract the frame or sweep 1fps caption crops around the estimate — the
same "search around a general timestamp area" workflow used to find Zorua.

Usage:
    python3 find_pokemon.py Zorua
    python3 find_pokemon.py ゾロア --scan scan/zorua
    python3 find_pokemon.py Lizardon --video ../video/pokemon-all-stars-1025.1080p.mp4 --extract lizardon.jpg
    python3 find_pokemon.py "nidoran"        # suggests Nidoran♂ / Nidoran♀

The --video option extracts from a local file instead of streaming
(video/ is gitignored; keep it out of the repo).
"""

import argparse
import difflib
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_subs import parse_vtt
from extract_frame import stream_url

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
NAMES_JSON = os.path.join(ROOT, "names.json")
VTT = os.path.join(ROOT, "subs", "PqOBtBOsB_I.ja-orig.vtt")
BLOCKS_JSON = os.path.join(ROOT, "blocks.json")
SAMPLES_JSON = os.path.join(ROOT, "samples", "samples.json")

# Burned-in caption region at 1080p (see README); scaled by video height.
CAPTION_CROP_1080P = (720, 105, 600, 968)  # w, h, x, y


def load_names():
    with open(NAMES_JSON, encoding="utf-8") as f:
        return json.load(f)


def hira_to_kata(s: str) -> str:
    return "".join(
        chr(ord(c) + 0x60) if "\u3041" <= c <= "\u3096" else c for c in s
    )


def resolve(query, names):
    """Return (index, None) on exact match, or (None, [suggestions])."""
    q = query.strip()
    if any("\u3040" <= c <= "\u30ff" or "\uff61" <= c <= "\uff9f" for c in q):
        qk = hira_to_kata(q)
        for i, n in enumerate(names):
            if n["ja"] == qk:
                return i, None
        pool = [n["ja"] for n in names]
        return None, difflib.get_close_matches(qk, pool, n=5, cutoff=0.6)
    ql = q.lower()
    hits = [i for i, n in enumerate(names) if n["en"].lower() == ql]
    hits += [i for i, n in enumerate(names)
             if n["romaji"].lower() == ql and i not in hits]
    if len(hits) == 1:
        return hits[0], None
    if len(hits) > 1:
        return None, [names[i]["en"] for i in hits]
    pool = [n["en"] for n in names] + [n["romaji"] for n in names]
    suggestions = list(dict.fromkeys(
        difflib.get_close_matches(q, pool, n=5, cutoff=0.6)))
    return None, suggestions


def build_anchors(names):
    """(lyric index, timestamp, label) points.

    Hand-verified samples are authoritative. Auto anchors come from exact
    lyric-name hits inside the auto-caption cues: the captions mangle most
    names, but the ones that survive verbatim still pin the timeline. Names
    are matched greedily in song order so offsets stay monotonic within each
    cue; sub-second rolling-duplicate cue slices are skipped.
    """
    samples = json.load(open(SAMPLES_JSON, encoding="utf-8"))
    ja_to_idx = {n["ja"]: i for i, n in enumerate(names)}
    hand = {}
    for s in samples:
        ja = s.get("name_ja") or s.get("japanese")
        if ja in ja_to_idx:
            hand[ja_to_idx[ja]] = (float(s["t"]), "verified sample")
    auto = {}
    for start, end, text in parse_vtt(VTT):
        if end - start < 1.0 or not text:
            continue
        pos = 0
        for i, n in enumerate(names):
            if i in hand or len(n["ja"]) < 4:
                continue
            j = text.find(n["ja"], pos)
            if j >= 0:
                t = start + (j / len(text)) * (end - start)
                if i not in auto or t < auto[i][0]:
                    auto[i] = (t, f"caption {fmt(start)}")
                pos = j + len(n["ja"])
    merged = dict(auto)
    merged.update(hand)  # hand-verified wins on conflict
    # Drop auto anchors that contradict the hand-verified scaffold: a block's
    # text can echo names from elsewhere in the song (e.g. block 16 repeats
    # early names at ~1049s), which would spike the interpolation.
    hkeys = sorted(hand)
    hts = [hand[k][0] for k in hkeys]
    slack = 60.0
    for i in list(merged):
        if i in hand:
            continue
        t = merged[i][0]
        if i <= hkeys[0]:
            ok = t <= hts[0] + slack
        elif i >= hkeys[-1]:
            ok = t >= hts[-1] - slack
        else:
            for (a, ta), (b, tb) in zip(zip(hkeys, hts), zip(hkeys[1:], hts[1:])):
                if a <= i <= b:
                    ok = ta - slack <= t <= tb + slack
                    break
        if not ok:
            del merged[i]
    return sorted((i, t, lbl) for i, (t, lbl) in merged.items())


def estimate(idx, anchors):
    """Interpolate (or extrapolate) a timestamp between anchors."""
    if idx <= anchors[0][0]:
        (i1, t1, l1), (i2, t2, l2) = anchors[0], anchors[1]
    elif idx >= anchors[-1][0]:
        (i1, t1, l1), (i2, t2, l2) = anchors[-2], anchors[-1]
    else:
        for (i1, t1, l1), (i2, t2, l2) in zip(anchors, anchors[1:]):
            if i1 <= idx <= i2:
                break
    t = t1 + (idx - i1) / (i2 - i1) * (t2 - t1)
    return t, (i1, t1, l1), (i2, t2, l2)


def block_around(t):
    """Describe where t falls relative to the 18 subtitle blocks."""
    blocks = json.load(open(BLOCKS_JSON, encoding="utf-8"))
    for b in blocks:
        if b["start"] <= t <= b["end"]:
            return f"inside block {b['index']} ({fmt(b['start'])} → {fmt(b['end'])})"
    prev = next((b for b in reversed(blocks) if b["end"] < t), None)
    nxt = next((b for b in blocks if b["start"] > t), None)
    if prev and nxt:
        return (f"between block {prev['index']} (ends {fmt(prev['end'])}) "
                f"and block {nxt['index']} (starts {fmt(nxt['start'])})")
    if nxt:
        return f"before block {nxt['index']} (starts {fmt(nxt['start'])})"
    return f"after block {prev['index']} (ends {fmt(prev['end'])})"


def fmt(t):
    m, s = divmod(t, 60)
    return f"{int(m):02d}:{s:05.2f}"


def video_height(src):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=height", "-of", "csv=p=0", src],
        capture_output=True, text=True, check=True,
    )
    return int(out.stdout.strip().splitlines()[0])


def extract_frame_at(src, t, out, crop=None):
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    vf = f"crop={crop[0]}:{crop[1]}:{crop[2]}:{crop[3]}" if crop else None
    cmd = ["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", src,
           "-frames:v", "1", "-q:v", "2"]
    if vf:
        cmd += ["-vf", vf]
    cmd.append(out)
    subprocess.run(cmd, check=True)


def scan_area(src, t, radius, outdir):
    h = video_height(src)
    s = h / 1080
    w, ch, x, y = (int(v * s) for v in CAPTION_CROP_1080P)
    os.makedirs(outdir, exist_ok=True)
    t0 = max(0, t - radius)
    dur = 2 * radius
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-ss", f"{t0:.2f}", "-i", src, "-t", f"{dur:.2f}",
         "-vf", f"fps=1,crop={w}:{ch}:{x}:{y}", "-q:v", "2",
         os.path.join(outdir, "cap_%04d.jpg")],
        check=True,
    )
    n = int(dur) + 1
    print(f"saved {n} caption crops to {outdir}/ "
          f"(t={t0:.0f}s..{t0 + dur:.0f}s, 1fps)")


def main():
    global _NAMES
    ap = argparse.ArgumentParser(description="Find a Pokemon's page timestamp.")
    ap.add_argument("name", help="English, romaji, or Japanese (kana) name")
    ap.add_argument("--video", default=None, help="local video file (default: stream)")
    ap.add_argument("--extract", default=None, metavar="OUT",
                    help="save the estimated frame to OUT")
    ap.add_argument("--scan", default=None, metavar="DIR",
                    help="save 1fps caption crops around the estimate to DIR")
    ap.add_argument("--radius", type=float, default=45,
                    help="scan radius in seconds (default: 45)")
    args = ap.parse_args()

    _NAMES = load_names()
    idx, suggestions = resolve(args.name, _NAMES)
    if idx is None:
        print(f"no match for {args.name!r}")
        if suggestions:
            print("did you mean: " + ", ".join(suggestions))
        sys.exit(1)
    n = _NAMES[idx]
    print(f"{n['en']} — {n['ja']} (romaji: {n['romaji']}) — "
          f"lyric {idx + 1}/1025")

    anchors = build_anchors(_NAMES)
    t_est, (i1, t1, l1), (i2, t2, l2) = estimate(idx, anchors)
    exact = next((a for a in anchors if a[0] == idx), None)
    if exact:
        _, t_est, lbl = exact
        how = lbl
    else:
        how = (f"between {_NAMES[i1]['ja']}@{t1:.1f}s ({l1}) and "
               f"{_NAMES[i2]['ja']}@{t2:.1f}s ({l2})")
    print(f"{block_around(t_est)} · estimated timestamp: {t_est:.1f}s [{how}]")

    src = None
    if args.extract or args.scan:
        src = args.video if args.video else stream_url(None)
    if args.extract:
        extract_frame_at(src, t_est, args.extract)
        print(f"saved {args.extract} @ t={t_est:.2f}s")
    elif args.scan:
        scan_area(src, t_est, args.radius, args.scan)
        print(f"flip through {args.scan}/ and look for the caption "
              f"reading「{n['ja']}」")
    else:
        print(f"frame: python3 scripts/extract_frame.py {t_est:.1f} out.jpg"
              + (f" --video {args.video}" if args.video else ""))
        dirname = "".join(c if c.isalnum() else "_" for c in n["en"]).lower()
        print(f"scan:  python3 scripts/find_pokemon.py {args.name} --scan "
              f"scan/{dirname}"
              + (f" --video {args.video}" if args.video else ""))


if __name__ == "__main__":
    main()
