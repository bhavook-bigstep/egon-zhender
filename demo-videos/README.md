# Demo videos

Narrated product-demo videos of the WS-1 PII-flagging console, produced with the
`demo-video` skill (Playwright capture + local Kokoro voice, no cloud, no keys).

The rendered `.mp4` and all capture intermediates (`out/`, `*.webm`, `*.wav`) are
**build artifacts** and are git-ignored — regenerate them from the recorder below.

## What's here

| File | Role |
| --- | --- |
| `console-tour.mjs` | The recorder: a full feature-by-feature walkthrough of the console, including a **live run** of one document (ingest → extract → OCR gate → detect → semantic → LLM → score), the Jobs monitor + results overlay, the Records review hub + explainable findings, custom recognizers + checksums, and the golden-truth evaluation. Voice-only, native/Retina (`dsf:2`). |

## Regenerate the video

The app must be running locally (`uvicorn app.main:app`, at `http://127.0.0.1:8000`)
with data already processed (the tour opens existing records and does one live run).

```bash
cd demo-videos
S=../.claude/skills/demo-video ; V=$S/scripts/voice

# 1. validate every selector + the flow (~40s; triggers one real live run of gold-0000)
PLAYWRIGHT_CORE=$(npm root -g)/playwright/node_modules/playwright-core/index.mjs \
  DEMO_BASE_URL=http://127.0.0.1:8000 FAST=1 node console-tour.mjs ~/demo-chrome-profile ./out

# 2. the real capture (native 4K)
PLAYWRIGHT_CORE=$(npm root -g)/playwright/node_modules/playwright-core/index.mjs \
  DEMO_BASE_URL=http://127.0.0.1:8000 node console-tour.mjs ~/demo-chrome-profile ./out record

# 3. voice (local Kokoro af_heart) + post
cp out/demo.cues.txt out/voice.cues.txt
python3 $V/tts_kokoro.py out/voice.cues.txt out/tts t
WEBM=$(ls out/page*.webm | tail -1)
ffmpeg -y -i "$WEBM" -vf fps=15 -fps_mode cfr -c:v libx264 -crf 21 -pix_fmt yuv420p -an out/raw.mp4
python3 $V/trimlead.py out/tts t "$(wc -l < out/voice.cues.txt)" out/trim
python3 $V/destagger.py out/demo.cues.txt out/trim t out/final_cues.txt out/final.srt
python3 $V/build-track.py out/final.srt out/trim t out/track.wav
bash    $V/mux.sh out/raw.mp4 out/track.wav "Prince Houston PII Console - Tour.mp4"
```

All data shown is the **synthetic golden set** (public-dataset-derived, no real PII);
matched content stays location-only in the capture.
