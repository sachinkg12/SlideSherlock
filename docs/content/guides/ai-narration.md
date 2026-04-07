---
id: ai-narration
title: AI Narration
sidebar_position: 5
---

# AI Narration

SlideSherlock's **AI Narration** feature uses a large language model (default: **GPT-4o-mini**) to rewrite the verified, evidence-grounded script into more natural-sounding presenter delivery — without breaking the no-hallucination guarantee.

This guide covers what AI narration does, how to enable it across all entry points, what it costs, what data leaves your machine, and what local alternatives are on the roadmap.

---

## What It Is

AI narration is implemented as a **dedicated pipeline stage**: `packages/core/stages/narrate.py` (`NarrateStage`). It runs **after** the verifier loop and **before** the audio (TTS) stage. It is completely **optional** — toggling it off skips the stage entirely and the pipeline remains free, deterministic, and offline-capable.

### Two-Pass Design

The whole point of AI narration is to give you natural, presenter-quality voice-over **without** giving up the verifier's grounding guarantees. SlideSherlock achieves this by separating *what to say* (Pass 1) from *how to say it* (Pass 2):

```
Pass 1 — Grounded template (deterministic, free)
   StubLLMProvider → script_generator
                  → verifier loop (PASS / REWRITE / REMOVE, max 3 iters)
                  → "verified script": every claim cites evidence_ids

Pass 2 — Natural rewrite (optional, paid)
   NarrateStage    → GPT-4o-mini
                  → rewrites each per-slide narration block in-place
                  → preserves all claims accepted by Pass 1
                  → bounded ThreadPoolExecutor parallelism

Audio stage      → TTS reads the rewritten narration
```

Because Pass 1 has already filtered out every ungrounded claim, Pass 2 only operates on text the verifier accepted. The model is prompted to **keep all factual content** and **only adjust phrasing, cadence, and presenter tone**. No new entities, claims, numbers, or evidence references can be introduced.

If a per-slide rewrite fails (rate limit, network error, malformed JSON), that slide **falls back to the original verified narration** — AI narration never blocks the pipeline.

---

## How to Enable It

AI narration is **orthogonal to quality presets**. You can enable it on a `draft` preset (cheap visuals + natural voice) or disable it on a `pro` preset (full visuals + deterministic voice for reproducible benchmarks).

### 1. Web UI

The Mission Control upload page exposes a dedicated **AI Narration toggle** next to the preset selector. Toggling it sends `ai_narration=true` to `POST /jobs/quick`.

### 2. CLI

```bash
# Enable AI narration with the pro preset
slidesherlock run deck.pptx --ai-narration --preset pro -o ./results/

# AI narration with draft preset (cheap visuals + natural voice)
slidesherlock run deck.pptx --ai-narration --preset draft
```

### 3. REST API — Quick submit

```bash
curl -X POST "http://localhost:8000/jobs/quick?ai_narration=true" \
  -F "file=@deck.pptx" \
  -F "preset=pro"
```

### 4. REST API — Three-step flow

Pass `ai_narration: true` inside `config_json` on `POST /jobs`:

```bash
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "...",
    "name": "Narrated demo",
    "config_json": {
      "preset": "pro",
      "ai_narration": true
    }
  }'
```

The flag is persisted to `job.config_json.ai_narration`, read by `run_pipeline()`, and surfaced to the NarrateStage as `ctx.config["ai_narration"]`.

---

## Worker Requirements

For AI narration to actually run, **all three** must be true on the worker:

1. The job has `ai_narration: true` in `config_json`
2. The worker process has `OPENAI_API_KEY` set in its environment
3. The worker process has `LLM_PROVIDER=openai` (or `auto` with the key present)

If any of these is missing, the NarrateStage logs a warning and the pipeline falls through to TTS using the original verified narration.

---

## Cost

The default model is **`gpt-4o-mini`**, chosen specifically because it gives natural presenter-style rewrites at a fraction of `gpt-4o`'s price.

| Model | Cost / slide *(approx.)* | 30-slide deck | 158-deck corpus *(LoC)* |
|---|---:|---:|---:|
| `gpt-4o-mini` (default) | **$0.001** | **$0.03** | ~$5 |
| `gpt-4o` | $0.01 | $0.30 | ~$50 |

Because each call rewrites a single per-slide narration block (a few hundred tokens in, a few hundred out), `gpt-4o-mini` is sufficient in almost all real-world cases. Override with `NARRATE_MODEL=gpt-4o` only when benchmarking against the strongest available model.

---

## Privacy

The NarrateStage **does not send slide images** to OpenAI under any circumstance. Image understanding is handled separately by the [Vision Provider](../architecture/providers#vision-provider) and runs as part of the Evidence stage (and only when explicitly enabled).

The NarrateStage sends only **text**:

| Sent to OpenAI | Not sent to OpenAI |
|---|---|
| The verified per-slide narration text | The PNG/JPG slide images |
| Speaker notes from the PPTX | The PPTX file itself |
| Evidence labels (e.g. `IMAGE_CAPTION`, `DIAGRAM_ENTITIES`) | Bounding boxes, hash IDs, internal job IDs |
| Slide numbers | Personally identifying job metadata |

If your slides contain text that must not leave your environment, **do not enable AI narration** — the deterministic StubLLMProvider runs locally and produces grounded narration without any network calls.

---

## Configuration Reference

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | _(required)_ | OpenAI API key. Read by NarrateStage at job time. |
| `LLM_PROVIDER` | `auto` | Set to `openai` (or leave `auto` with a key present) to activate. |
| `NARRATE_MODEL` | `gpt-4o-mini` | Model used for the rewrite. Set to `gpt-4o` for highest quality. |
| `NARRATE_PARALLEL` | `5` | Maximum concurrent OpenAI calls per job. NarrateStage uses `concurrent.futures.ThreadPoolExecutor` with this bound. |

### Why `requests`, not the `openai` SDK?

`NarrateStage` calls the OpenAI REST API using the **`requests` library directly**. The official `openai` Python SDK uses `httpx`, which deadlocks inside RQ's forked workers on macOS and on some Linux configurations (the underlying `anyio`/`httpx` event loop is not fork-safe). Using `requests` sidesteps the fork-safety issue completely.

This is also why the `verify` stage uses **deterministic rewrites only** (no LLM calls) — keeping all OpenAI calls inside the dedicated NarrateStage means we only have one place that needs to be fork-safe, retry-aware, and parallelism-bounded.

---

## Local Alternatives *(roadmap)*

For users who cannot or do not want to send any text to a third-party API, the AI narration design is intentionally model-agnostic. Adding a local LLM is straightforward because `NarrateStage` only needs an HTTP endpoint that returns chat completions.

Planned future work:

- **Ollama + Llama 3.1 8B Instruct** — fully offline, runs on a laptop GPU. Quality is lower than `gpt-4o-mini` but acceptable for many decks.
- **vLLM + Mistral / Qwen** — for self-hosted GPU servers with higher throughput.
- **llama.cpp** — for pure CPU inference on machines without a GPU.

The intended interface is a `LOCAL_LLM_BASE_URL` env var pointing at an OpenAI-compatible server. Contributions welcome — see `packages/core/stages/narrate.py` for the integration point.

---

## When *Not* to Use AI Narration

| Scenario | Recommendation |
|---|---|
| Reproducible benchmarks for a paper | **Off** — keeps the script bit-identical across reruns |
| Automated CI / regression tests | **Off** — avoids API cost and flakiness |
| Highly sensitive slide content | **Off** — keeps everything local |
| Internal demos and stakeholder reviews | **On** — natural delivery noticeably improves perceived quality |
| Public-facing explainer videos | **On** with `gpt-4o-mini`, optionally `gpt-4o` |
| Multi-language (l2) variants | **On** — translated text especially benefits from a natural rewrite |

---

## See Also

- [Pipeline Stages → Narrate](../architecture/pipeline-stages) — implementation details
- [Provider System → LLM Provider](../architecture/providers#llm-provider) — two-pass design
- [Quality Presets](../configuration/quality-presets) — why AI narration is orthogonal to presets
- [Submitting Jobs](submitting-jobs) — all four entry points for enabling AI narration
