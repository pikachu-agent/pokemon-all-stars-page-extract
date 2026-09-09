#!/usr/bin/env python3
"""Parse the YouTube auto-caption VTT for the Pokemon All-Stars 1025 video and
find the time windows where Pokemon names are being rapped (i.e. where the
illustrated pages flip by on screen).

The auto captions mangle the fast rap (names are concatenated katakana with
STT errors), so we treat each long katakana-dense cue as a "name block" and
merge rolling duplicate cues into a single window.

Usage:
    python3 parse_subs.py subs/PqOBtBOsB_I.ja-orig.vtt [--json blocks.json]

Outputs a list of (start, end, text) windows and prints a summary.
"""

import json
import re
import sys

VTT_TS = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})\.(\d{3}) --> (\d{2}):(\d{2}):(\d{2})\.(\d{3})"
)
KARAOKE = re.compile(r"<[^>]*>")
MARKERS = ("[音楽]", "[歌声]")


def to_seconds(h, m, s, ms):
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def clean_text(raw: str) -> str:
    text = KARAOKE.sub("", raw)
    for mk in MARKERS:
        text = text.replace(mk, "")
    # drop cue settings line remnants
    text = text.replace("align:start position:0%", "")
    return "".join(text.split())


def is_name_block(text: str) -> bool:
    if len(text) < 40:
        return False
    kata = sum(1 for ch in text if "\u30a0" <= ch <= "\u30ff")
    # name blocks are dense katakana (the rap); lyric lines are mostly
    # hiragana/kanji
    return kata / max(len(text), 1) > 0.55


def parse_vtt(path: str):
    with open(path, encoding="utf-8") as f:
        content = f.read()
    cues = []
    for block in re.split(r"\n\s*\n", content):
        m = VTT_TS.search(block)
        if not m:
            continue
        start = to_seconds(*m.groups()[:4])
        end = to_seconds(*m.groups()[4:])
        text = clean_text(block[m.end():])
        cues.append((start, end, text))
    return cues


def coalesce(cues):
    """Merge consecutive cues that belong to the same name block.

    The auto captions emit rolling duplicates: the same lyric line is
    re-emitted every few hundred ms with tiny extensions. Merge cues whose
    texts overlap heavily and which are close in time.
    """
    blocks = []
    for start, end, text in cues:
        if not is_name_block(text):
            continue
        if blocks:
            ps, pe, ptext = blocks[-1]
            # same block if texts share a long common substring or one
            # contains the other, and the gap is small
            overlap = (
                text in ptext
                or ptext in text
                or any(len(piece) > 30 and piece in ptext for piece in [text])
            )
            if overlap and start - pe < 3.0:
                # extend window, keep the longest text seen
                if len(text) > len(ptext):
                    ptext = text
                blocks[-1] = (ps, max(pe, end), ptext)
                continue
        blocks.append((start, end, text))
    return blocks


def fmt(t: float) -> str:
    h, rem = divmod(int(t), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def main():
    path = sys.argv[1]
    blocks = coalesce(parse_vtt(path))
    total = sum(e - s for s, e, _ in blocks)
    print(f"name blocks: {len(blocks)}  total window: {total:.0f}s")
    for i, (s, e, text) in enumerate(blocks):
        print(f"[{i:3d}] {fmt(s)} --> {fmt(e)}  ({e - s:5.1f}s) {text[:60]}…")
    if "--json" in sys.argv:
        out = sys.argv[sys.argv.index("--json") + 1]
        with open(out, "w", encoding="utf-8") as f:
            json.dump(
                [
                    {"index": i, "start": s, "end": e, "text": t}
                    for i, (s, e, t) in enumerate(blocks)
                ],
                f,
                ensure_ascii=False,
                indent=1,
            )
        print(f"wrote {out}")


if __name__ == "__main__":
    main()
