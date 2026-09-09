# pokemon-all-stars-page-extract

Extract the illustrated album pages for all 1025 Pokémon from the official
music video [オーイシマサヨシ - ポケモンオールスターズ1025](https://www.youtube.com/watch?v=PqOBtBOsB_I)
(Pokémon official YouTube channel, 22:03).

The video flips through a scrapbook with one decorated page per Pokémon while
the song raps all 1025 names.

## What we learned

- **There is no manual Japanese subtitle track** — only YouTube auto-captions
  (`ja-orig`). They are speech-to-text of a very fast rap: names come out as
  one concatenated katakana blob with transcription errors
  (e.g. `ピカチュウドランピジョンコダック…`). Usable for *when* names are
  sung, not for *which* name is on screen.
- **Each page has the Pokémon's Japanese name burned into the video** at the
  bottom center (e.g. `ヤドラン`, `ガブリアス`). This is the reliable
  name→frame source, not the subtitles.
- The subtitle name order matches the on-screen page order, and pages flip
  roughly once per second.
- `scripts/parse_subs.py` finds 18 name-rap windows (113 s total) from the
  auto-captions — good coarse "around what time" anchors.
- yt-dlp needs a JS runtime for YouTube's player challenge: install
  [deno](https://deno.land/) and put it on `PATH`, otherwise you get
  "Sign in to confirm you're not a bot" errors. (The `android` player client
  also works as a fallback, at lower resolution.)

## Scripts

```bash
# 1. Download the Japanese auto-caption track
~/workspace/yt-venv/bin/yt-dlp --skip-download --write-subs \
    --sub-langs ja-orig -o "subs/%(id)s.%(ext)s" \
    "https://www.youtube.com/watch?v=PqOBtBOsB_I"

# 2. Find the name-rap time windows
python3 scripts/parse_subs.py subs/PqOBtBOsB_I.ja-orig.vtt --json blocks.json

# 3. Extract a frame at a timestamp (streams, no full download)
export PATH="$HOME/.deno/bin:$PATH"
python3 scripts/extract_frame.py 90.3 samples/flittle.jpg
```

## Samples

Six random pages (seed 42 over the 18 subtitle name blocks), identified from
the burned-in captions:

| file | JP | EN | t |
|---|---|---|---|
| `samples/rapidash.jpg` | ギャロップ | Rapidash | 17.9 s |
| `samples/flittle.jpg` | ヒラヒナ | Flittle | 90.3 s |
| `samples/corphish.jpg` | ヘイガニ | Corphish | 199.7 s |
| `samples/pincurchin.jpg` | バチンウニ | Pincurchin | 553.7 s |
| `samples/raticate.jpg` | ラッタ | Raticate | 925.7 s |
| `samples/arctovish.jpg` | ウオチルドン | Arctovish | 1223.9 s |

Details in `samples/samples.json`.

## Going further (all 1025)

1. Sample one frame per second across the whole video (accurate seek: put
   `-ss` *after* `-i`, or download the video once — fast `-ss` before `-i`
   lands on the nearest keyframe, ±0.5 s).
2. OCR the bottom-center caption region (`crop=480:70:400:645` at 720p) to
   read the Japanese name per frame.
3. Dedupe consecutive identical names → one timestamp per Pokémon.
