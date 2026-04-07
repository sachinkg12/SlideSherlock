---
id: quality-presets
title: Quality Presets
sidebar_position: 2
---

# Quality Presets

SlideSherlock ships with three named quality presets that configure the entire pipeline for different speed/quality trade-offs. A preset sets a bundle of environment variables atomically — you set one variable and the pipeline adjusts accordingly.

---

## Choosing a Preset

```bash
# Apply preset before starting the worker
SLIDESHERLOCK_PRESET=draft    make worker   # fastest — development / CI
SLIDESHERLOCK_PRESET=standard make worker   # balanced — demo / review
SLIDESHERLOCK_PRESET=pro      make worker   # highest quality — production
```

---

## Preset Comparison

| Setting | `draft` | `standard` | `pro` |
|---|:---:|:---:|:---:|
| Vision (image analysis) | Off | Off | **On** |
| AI Narration *(toggled separately)* | Off (toggle) | Off (toggle) | Off (toggle) |
| BGM | Off | Off | **On** |
| BGM Ducking | — | — | **On** |
| Transitions | Cut | Crossfade | Crossfade |
| Subtitles (SRT burn-in) | Off | **On** | **On** |
| On-Screen Notes | Off | **On** | **On** |
| Intro Card | Off | **On** | **On** |
| Outro Card | Off | **On** | **On** |
| Loudness Normalisation | Off | **On** | **On** |
| OpenAI API required | ✗ | ✗ | ✓ (recommended) |
| Approx. extra cost per slide | $0 | $0 | ~$0.01–0.05 |

:::important AI Narration is orthogonal to presets
The **AI Narration** feature (GPT-4o-mini rewrite of the verified script for natural delivery) is **not bound to any preset**. It is toggled independently via:

- The **AI Narration toggle** on the upload page in the web UI
- The `--ai-narration` flag on the CLI: `slidesherlock run deck.pptx --ai-narration --preset pro`
- The `ai_narration` query parameter on `POST /jobs/quick`
- The `config_json.ai_narration` field on `POST /jobs`

This means you can enable AI narration on a `draft` run (cheap visuals + natural voice) or disable it on a `pro` run (full visuals + deterministic voice for reproducibility). See the [AI Narration guide](../guides/ai-narration) for details.
:::

---

## Draft Preset

Best for: **rapid iteration, CI pipelines, offline development**

```bash
SLIDESHERLOCK_PRESET=draft make worker
```

Environment variables applied:

```bash
VISION_ENABLED=0
AUDIO_BGM_ENABLED=0
VIDEO_TRANSITION=cut
ON_SCREEN_NOTES_ENABLED=0
SUBTITLES_ENABLED=0
VIDEO_INTRO_ENABLED=0
VIDEO_OUTRO_ENABLED=0
AUDIO_LOUDNESS_NORMALIZE=0
```

The stub LLM and stub TTS providers are used by default. Output is a raw cut video with no visual enhancements — purely for verifying pipeline correctness.

---

## Standard Preset

Best for: **stakeholder demos, internal reviews, presentations**

```bash
SLIDESHERLOCK_PRESET=standard make worker
```

Environment variables applied:

```bash
VISION_ENABLED=0
AUDIO_BGM_ENABLED=0
VIDEO_TRANSITION=crossfade
ON_SCREEN_NOTES_ENABLED=1
SUBTITLES_ENABLED=1
VIDEO_INTRO_ENABLED=1
VIDEO_OUTRO_ENABLED=1
AUDIO_LOUDNESS_NORMALIZE=1
```

Produces a polished video with on-screen notes, subtitles, smooth crossfade transitions, and loudness-normalised audio. Does not require an OpenAI API key.

---

## Pro Preset

Best for: **external distribution, published content, training material**

```bash
SLIDESHERLOCK_PRESET=pro make worker
```

Environment variables applied:

```bash
VISION_ENABLED=1
ON_SCREEN_NOTES_ENABLED=1
VIDEO_TRANSITION=crossfade
SUBTITLES_ENABLED=1
VIDEO_INTRO_ENABLED=1
VIDEO_OUTRO_ENABLED=1
AUDIO_BGM_ENABLED=1
AUDIO_BGM_DUCKING=1
AUDIO_LOUDNESS_NORMALIZE=1
```

Enables the full vision pipeline (GPT-4o image understanding), background music with narration ducking, and full loudness normalisation. Requires `OPENAI_API_KEY` for best results — falls back to stubs if not set.

:::tip Cost control
Enable `VISION_CACHE_ENABLED=true` (the default) to avoid re-charging the vision API for identical images across re-runs of the same presentation.
:::

---

## Per-Job Preset via config_json

Presets can also be applied at the job level via the `config_json` field, independently of the worker's environment:

```bash
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "...",
    "name": "Pro quality run",
    "config_json": {
      "preset": "pro",
      "vision": {
        "enabled": true,
        "force_kind_by_slide": {
          "3": "DIAGRAM",
          "5": "PHOTO"
        }
      }
    }
  }'
```

`force_kind_by_slide` overrides the automatic image classifier for specific slides (1-indexed).

---

## Overriding Individual Variables

Preset values can be overridden by individual environment variables set after the preset is applied. For example, to use the `pro` preset but disable BGM:

```bash
SLIDESHERLOCK_PRESET=pro AUDIO_BGM_ENABLED=0 make worker
```

Variables set in `.env` take lower precedence than variables set on the command line.
