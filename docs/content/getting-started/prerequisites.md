---
id: prerequisites
title: Prerequisites
sidebar_position: 1
---

# Prerequisites

Before installing SlideSherlock, ensure the following system dependencies are present on your machine. The `make doctor` command (available once the virtual environment is created) validates all of them automatically.

---

## System Requirements

| Requirement | Minimum Version | Purpose |
|---|---|---|
| **Python** | 3.11 (3.12 recommended) | Runtime for the entire pipeline |
| **Docker** + **Docker Compose** | Docker 24+ | Postgres, Redis, MinIO containers |
| **LibreOffice** | 7.x+ | PPTX → PDF conversion |
| **Poppler** (`pdftoppm`) | 21+ | PDF → PNG rasterisation |
| **FFmpeg** | 5+ | Video encoding, transitions, audio |
| **Node.js** | 18+ | Only needed to build / serve this documentation site |

---

## Python

Python **3.12 is recommended** for best compatibility. Python 3.11 is the minimum supported version. Python 3.14+ may have compatibility issues with some dependencies.

```bash
# Check your version
python3 --version

# macOS — install via pyenv (recommended)
brew install pyenv
pyenv install 3.12.4
pyenv local 3.12.4

# Ubuntu / Debian
sudo apt-get install python3.12 python3.12-venv
```

---

## Docker and Docker Compose

Docker is required to run the three infrastructure services (PostgreSQL, Redis, MinIO) via `docker-compose.yml`.

```bash
# macOS — install Docker Desktop
brew install --cask docker

# Ubuntu
sudo apt-get install docker-ce docker-compose-plugin

# Verify
docker --version
docker compose version
```

:::tip Port availability
The services bind to specific ports. Run `make check-ports` after the virtual environment is set up to confirm they are free.

| Service | Port |
|---|---|
| PostgreSQL | 5433 |
| Redis | 6379 |
| MinIO API | 9000 |
| MinIO Console | 9001 |
| pgAdmin (optional) | 5050 |
:::

---

## LibreOffice

LibreOffice is invoked as a headless subprocess to convert `.pptx` files to PDF. The pipeline will fail at the rendering stage without it.

```bash
# macOS
brew install --cask libreoffice

# Ubuntu / Debian
sudo apt-get install libreoffice

# CentOS / RHEL
sudo yum install libreoffice

# Verify (macOS)
/Applications/LibreOffice.app/Contents/MacOS/soffice --version
```

:::info macOS symlink
If `libreoffice` is not found on `$PATH`, create a symlink:
```bash
sudo ln -s /Applications/LibreOffice.app/Contents/MacOS/soffice /usr/local/bin/libreoffice
```
:::

---

## Poppler

Poppler provides `pdftoppm`, which rasterises PDF pages to PNG at 150 DPI.

```bash
# macOS
brew install poppler

# Ubuntu / Debian
sudo apt-get install poppler-utils

# Verify
pdftoppm -v
```

---

## FFmpeg

FFmpeg handles all video operations: overlay rendering, transitions, audio mixing, BGM ducking, subtitles, and final composition.

```bash
# macOS
brew install ffmpeg

# Ubuntu / Debian
sudo apt-get install ffmpeg

# Verify
ffmpeg -version
ffprobe -version
```

---

## Tesseract OCR (Optional)

Tesseract is only required when `VISION_ENABLED=1` and the vision graph builder is active. If not installed, the vision graph stage is skipped gracefully.

```bash
# macOS
brew install tesseract

# Ubuntu / Debian
sudo apt-get install tesseract-ocr
```

---

## OpenAI API Key (Optional)

SlideSherlock ships with **stub providers** for LLM, vision, and TTS. The pipeline runs end-to-end without any API keys — stubs return deterministic template narration and empty audio. To enable real AI-powered features:

| Feature | Environment Variable | Provider |
|---|---|---|
| Vision captioning + diagram understanding | `OPENAI_API_KEY` + `VISION_PROVIDER=openai` | GPT-4o |
| LLM script generation + rewriting | `OPENAI_API_KEY` | GPT-4o |
| OpenAI TTS narration | `OPENAI_API_KEY` | OpenAI TTS |
| ElevenLabs TTS | `ELEVENLABS_API_KEY` | ElevenLabs |
| macOS system TTS (offline) | `USE_SYSTEM_TTS=true` | macOS `say` |

---

## Checking All Dependencies

Once the virtual environment is created (see [Installation](installation)), run:

```bash
make doctor
```

Example output:
```
✅ Python 3.12.4
✅ LibreOffice 7.6.4.1
✅ FFmpeg 6.1
✅ FFprobe 6.1
✅ pdftoppm (Poppler 23.12)
⚠️  Tesseract not found — vision graph disabled (non-fatal)
✅ python-pptx 0.6.23
✅ Pillow 10.2.0
✅ pydub 0.25.1
```
