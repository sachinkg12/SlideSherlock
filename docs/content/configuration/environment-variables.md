---
id: environment-variables
title: Environment Variables
sidebar_position: 1
---

# Environment Variables

All configuration is managed through environment variables. Copy `.env.example` to `.env` and edit the values you need. The `.env` file is git-ignored and will not be committed.

```bash
cp .env.example .env
```

The variables on this page are grouped into eight categories:

1. **Storage / Infrastructure** — Postgres, Redis, MinIO
2. **LLM** — OpenAI script generation, narration rewrite
3. **Vision** — Image captioning, diagram understanding, caching
4. **TTS** — System and cloud text-to-speech
5. **Audio** — Loudness normalisation, background music
6. **Video** — Composition, transitions, intro/outro
7. **Notes** — On-screen burned-in narration captions
8. **Pipeline** — Render performance, presets, verifier loop

---

## Infrastructure

These variables configure the three Docker Compose services. The defaults match the `docker-compose.yml` configuration and require no changes for local development.

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://slidesherlock:slidesherlock@localhost:5433/slidesherlock` | PostgreSQL connection string |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection string |
| `MINIO_ENDPOINT` | `http://localhost:9000` | MinIO API endpoint |
| `MINIO_ACCESS_KEY` | `minioadmin` | MinIO access key |
| `MINIO_SECRET_KEY` | `minioadmin` | MinIO secret key |
| `MINIO_BUCKET` | `slidesherlock` | Bucket name for all artifacts |

---

## API Server

| Variable | Default | Description |
|---|---|---|
| `PORT` | `8000` | FastAPI server port |
| `HOST` | `0.0.0.0` | FastAPI server bind address |

---

## LLM

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | _(empty)_ | OpenAI API key. Enables LLM, vision, OpenAI TTS, and AI narration when set. |
| `LLM_PROVIDER` | `auto` | `auto` (use OpenAI when key present, else stub), `stub`, or `openai` |
| `OPENAI_LLM_MODEL` | `gpt-4o` | Model for script generation and verifier rewrites |
| `OPENAI_LLM_TEMPERATURE` | `0.3` | Generation temperature |
| `OPENAI_LLM_TIMEOUT_SECONDS` | `60` | Request timeout (seconds) |
| `NARRATE_MODEL` | `gpt-4o-mini` | Model used by the dedicated NarrateStage to rewrite verified scripts for natural delivery |
| `NARRATE_PARALLEL` | `5` | Maximum concurrent OpenAI calls per job in NarrateStage (uses ThreadPoolExecutor) |
| `VERIFIER_MAX_ITERS` | `3` | Maximum rewrite iterations in the verifier loop |

---

## Vision

| Variable | Default | Description |
|---|---|---|
| `VISION_ENABLED` | `1` | Enable/disable vision pipeline. Set to `0` for draft preset. |
| `VISION_PROVIDER` | `stub` | Vision provider: `stub` or `openai` |
| `VISION_EXTRACTOR_PROVIDER` | same as `VISION_PROVIDER` | Override the extractor provider independently |
| `VISION_CACHE_ENABLED` | `true` | Cache vision results in MinIO by image hash + model + prompt version |
| `VISION_CACHE_PREFIX` | `jobs/{job_id}/cache/vision/` | MinIO key prefix for vision cache |
| `VISION_MIN_CONFIDENCE` | `0.65` | Confidence threshold below which hedging language is required |
| `OPENAI_VISION_MODEL` | `gpt-4o-mini` | OpenAI model for vision calls (was `gpt-4o`; downgraded for cost — ~15× cheaper) |
| `OPENAI_VISION_TEMPERATURE` | `0` | Temperature for vision model |
| `OPENAI_VISION_TIMEOUT_SECONDS` | `60` | Request timeout (seconds) |

---

## Text-to-Speech

| Variable | Default | Description |
|---|---|---|
| `USE_SYSTEM_TTS` | `false` | Use macOS `say` / Linux `espeak` for offline TTS. **Required `true` on macOS RQ workers** to avoid pyttsx3 fork hang. |
| `OBJC_DISABLE_INITIALIZE_FORK_SAFETY` | _(unset)_ | Set to `YES` on macOS workers (auto-set by `make worker`) |
| `OPENAI_TTS_MODEL` | `tts-1` | OpenAI TTS model: `tts-1` or `tts-1-hd` |
| `OPENAI_TTS_VOICE` | `alloy` | OpenAI TTS voice: `alloy`, `echo`, `fable`, `onyx`, `nova`, `shimmer` |
| `ELEVENLABS_API_KEY` | _(empty)_ | ElevenLabs API key |
| `ELEVENLABS_VOICE_ID` | _(empty)_ | ElevenLabs voice ID |

---

## Audio

| Variable | Default | Description |
|---|---|---|
| `AUDIO_MODE` | `generate` | `generate` (TTS) or `use_supplied` (pre-recorded WAVs) |
| `AUDIO_LOUDNESS_NORMALIZE` | `1` | Apply loudness normalisation to narration audio |
| `AUDIO_LUFS_TARGET` | `-23.0` | Target loudness in LUFS (EBU R128 standard) |
| `AUDIO_SAMPLE_RATE` | `48000` | Output audio sample rate in Hz |
| `AUDIO_BGM_ENABLED` | `0` | Enable background music track |
| `AUDIO_BGM_PATH` | _(empty)_ | Path to BGM audio file (WAV/MP3); falls back to bundled royalty-free track if empty |
| `AUDIO_BGM_VOLUME` | `0.15` | BGM gain (linear, 0.0–1.0) when not ducking |
| `AUDIO_BGM_DUCKING` | `0` | Duck BGM volume during narration |
| `AUDIO_BGM_DUCK_VOLUME` | `0.05` | BGM gain during narration when ducking |
| `AUDIO_BGM_TARGET_LUFS` | `-30.0` | BGM loudness target when ducking |
| `AUDIO_BGM_FADE_IN_MS` | `1000` | BGM fade-in duration in milliseconds |
| `AUDIO_BGM_FADE_OUT_MS` | `1500` | BGM fade-out duration in milliseconds |

---

## Video

| Variable | Default | Description |
|---|---|---|
| `VIDEO_TRANSITION` | `cut` | Transition type: `cut`, `crossfade`, `fade`, or `slide` |
| `VIDEO_TRANSITION_MS` | `500` | Crossfade / fade duration in milliseconds |
| `VIDEO_INTRO_ENABLED` | `0` | Add intro title card |
| `VIDEO_INTRO_DURATION` | `3.0` | Intro duration in seconds |
| `VIDEO_INTRO_TITLE` | _(deck title)_ | Title text for intro card |
| `VIDEO_INTRO_SUBTITLE` | _(empty)_ | Subtitle text for intro card |
| `VIDEO_INTRO_BG_COLOR` | `#0a0a0a` | Background colour for intro card |
| `VIDEO_OUTRO_ENABLED` | `0` | Add outro title card |
| `VIDEO_OUTRO_DURATION` | `3.0` | Outro duration in seconds |
| `VIDEO_OUTRO_TITLE` | `Thank you` | Outro title text |
| `VIDEO_OUTRO_SUBTITLE` | _(empty)_ | Outro subtitle text |
| `VIDEO_LOUDNESS_NORMALIZE` | `0` | Apply final loudness normalisation (`ffmpeg-normalize`) to output video |
| `VIDEO_LOUDNESS_TARGET_LUFS` | `-16.0` | Target LUFS for the final video (broadcast standard) |

---

## On-Screen Notes

| Variable | Default | Description |
|---|---|---|
| `ON_SCREEN_NOTES_ENABLED` | `0` | Render narration text as on-screen captions |
| `ON_SCREEN_NOTES_FONT_SIZE` | `24` | Font size in pixels |
| `ON_SCREEN_NOTES_COLOR` | `white` | Text colour (HTML name or hex) |
| `ON_SCREEN_NOTES_BG_COLOR` | `#000000aa` | Background panel colour (with alpha) |
| `ON_SCREEN_NOTES_POSITION` | `bottom` | Text position: `top` or `bottom` |
| `ON_SCREEN_NOTES_PADDING` | `20` | Padding around the text in pixels |
| `ON_SCREEN_NOTES_MAX_WIDTH_PCT` | `0.9` | Maximum text width as a fraction of video width |
| `ON_SCREEN_NOTES_LINE_SPACING` | `4` | Extra pixels between text lines |
| `ON_SCREEN_NOTES_FONT_PATH` | _(system default)_ | Absolute path to a `.ttf` font file |

---

## Subtitles

| Variable | Default | Description |
|---|---|---|
| `SUBTITLES_ENABLED` | `0` | Generate and burn SRT subtitles into the video |

---

## Quality Preset Shortcut

Instead of setting individual variables, apply a preset:

| Variable | Options | Description |
|---|---|---|
| `SLIDESHERLOCK_PRESET` | `draft`, `standard`, `pro` | Apply a named quality preset (see [Quality Presets](quality-presets)) |

Preset variables override individual settings. Individual settings can further override preset values.

---

## Render Performance

| Variable | Default | Description |
|---|---|---|
| `RENDER_DPI` | `150` | DPI for PDF → PNG conversion (higher = larger files, sharper video) |
| `RENDER_VIDEO_WIDTH` | `1920` | Output video width in pixels |
| `RENDER_VIDEO_HEIGHT` | `1080` | Output video height in pixels |
| `RENDER_VIDEO_FPS` | `30` | Output video frame rate |
