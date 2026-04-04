.PHONY: help up down test lint migrate worker api install setup check-ports clean test-redis lint-fix migrate-create check-system-deps demo doctor preset-draft preset-standard preset-pro run

help:
	@echo "SlideSherlock - PPTX to Narrated Video Pipeline"
	@echo ""
	@echo "Available commands:"
	@echo "  make doctor          - Run dependency checks (LibreOffice, FFmpeg, Poppler, Tesseract)"
	@echo "  make preset-draft    - Apply draft preset (no vision, no bgm, cut transitions)"
	@echo "  make preset-standard - Apply standard preset (notes overlay + crossfade + subtitles)"
	@echo "  make preset-pro      - Apply pro preset (vision + bgm ducking + loudness normalize)"
	@echo "  make check-system-deps - Check if system dependencies are installed"
	@echo "  make setup      - Check system deps, create venv and install all Python dependencies"
	@echo "  make install    - Install/update dependencies in virtual environment"
	@echo "  make up         - Start docker-compose services"
	@echo "  make down       - Stop docker-compose services"
	@echo "  make migrate    - Run database migrations"
	@echo "  make worker     - Start RQ worker process"
	@echo "  make api        - Start FastAPI server"
	@echo "  make run F=deck.pptx - Run pipeline on a PPTX file (no Redis needed)"
	@echo "  make demo       - Run full pipeline on sample PPTX and produce output/demo/final.mp4"
	@echo "  make test       - Run tests"
	@echo "  make lint       - Run linters"
	@echo "  make check-ports - Check if required ports are available"
	@echo "  make test-redis  - Test Redis connection"
	@echo "  make clean      - Clean build artifacts"

doctor:
	@if [ ! -d "venv" ]; then \
		echo "ERROR: Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	@PYTHONPATH=$$(pwd):$$(pwd)/packages/core venv/bin/python scripts/slidesherlock_cli.py doctor

preset-draft:
	@echo "To use draft preset: SLIDESHERLOCK_PRESET=draft make worker"
	@echo "Or: eval \$$(PYTHONPATH=$$(pwd):$$(pwd)/packages/core venv/bin/python scripts/slidesherlock_cli.py preset draft --export) && make worker"

preset-standard:
	@echo "To use standard preset: SLIDESHERLOCK_PRESET=standard make worker"
	@echo "Or: eval \$$(PYTHONPATH=$$(pwd):$$(pwd)/packages/core venv/bin/python scripts/slidesherlock_cli.py preset standard --export) && make worker"

preset-pro:
	@echo "To use pro preset: SLIDESHERLOCK_PRESET=pro make worker"
	@echo "Or: eval \$$(PYTHONPATH=$$(pwd):$$(pwd)/packages/core venv/bin/python scripts/slidesherlock_cli.py preset pro --export) && make worker"

check-system-deps:
	@echo "Checking system dependencies..."
	@echo ""
	@echo "Python:"
	@if command -v python3.12 > /dev/null 2>&1 || command -v python3.11 > /dev/null 2>&1 || command -v python3 > /dev/null 2>&1; then \
		echo "  ✅ Python found"; \
	else \
		echo "  ❌ Python 3.11+ not found"; \
	fi
	@echo ""
	@echo "LibreOffice (required for PPTX to PDF conversion):"
	@if command -v libreoffice > /dev/null 2>&1; then \
		echo "  ✅ LibreOffice found: $$(libreoffice --version 2>/dev/null | head -1 || echo 'installed')"; \
	elif [ -f "/Applications/LibreOffice.app/Contents/MacOS/soffice" ]; then \
		echo "  ✅ LibreOffice found (macOS app bundle)"; \
		echo "     Note: Using /Applications/LibreOffice.app/Contents/MacOS/soffice"; \
	elif [ -f "/Applications/LibreOffice.app/Contents/MacOS/soffice.bin" ]; then \
		echo "  ✅ LibreOffice found (macOS app bundle)"; \
		echo "     Note: Using /Applications/LibreOffice.app/Contents/MacOS/soffice.bin"; \
	else \
		echo "  ❌ LibreOffice not found"; \
		echo "     Install with: brew install --cask libreoffice (macOS)"; \
		echo "                   sudo apt-get install libreoffice (Ubuntu/Debian)"; \
		echo ""; \
		echo "     If installed via Homebrew cask, you may need to create a symlink:"; \
		echo "     sudo ln -s /Applications/LibreOffice.app/Contents/MacOS/soffice /usr/local/bin/libreoffice"; \
	fi
	@echo ""
	@echo "Poppler (required for PDF to PNG conversion):"
	@if command -v pdftoppm > /dev/null 2>&1; then \
		echo "  ✅ Poppler found: $$(pdftoppm -v 2>&1 | head -1 || echo 'installed')"; \
	else \
		echo "  ❌ Poppler not found"; \
		echo "     Install with: brew install poppler (macOS)"; \
		echo "                   sudo apt-get install poppler-utils (Ubuntu/Debian)"; \
	fi
	@echo ""
	@echo "Docker:"
	@if command -v docker > /dev/null 2>&1; then \
		echo "  ✅ Docker found: $$(docker --version)"; \
	else \
		echo "  ❌ Docker not found"; \
	fi
	@echo ""

setup: check-system-deps
	@echo "Creating virtual environment..."
	@if [ ! -d "venv" ]; then \
		if command -v python3.12 > /dev/null 2>&1; then \
			echo "Using Python 3.12 (recommended for compatibility)"; \
			python3.12 -m venv venv; \
		elif command -v python3.11 > /dev/null 2>&1; then \
			echo "Using Python 3.11 (recommended for compatibility)"; \
			python3.11 -m venv venv; \
		elif command -v python3 > /dev/null 2>&1; then \
			echo "Using python3 (may have compatibility issues with Python 3.14+)"; \
			python3 -m venv venv; \
		elif command -v python > /dev/null 2>&1; then \
			echo "Using python (may have compatibility issues with Python 3.14+)"; \
			python -m venv venv; \
		else \
			echo "ERROR: Python 3.11+ is required but not found"; \
			exit 1; \
		fi \
	else \
		echo "Virtual environment already exists at venv"; \
	fi
	@echo "Installing Python dependencies from requirements.txt..."
	@venv/bin/pip install --upgrade pip
	@venv/bin/pip install -r requirements.txt
	@echo ""
	@echo "✅ Virtual environment created and all Python dependencies installed!"
	@echo ""
	@echo "To activate the virtual environment, run:"
	@echo "  source venv/bin/activate"
	@echo ""
	@echo "Or use the Makefile commands which will automatically use the venv."

install:
	@if [ ! -d "venv" ]; then \
		echo "ERROR: Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	@echo "Installing/updating dependencies in virtual environment..."
	@venv/bin/pip install --upgrade pip
	@venv/bin/pip install -r requirements.txt

check-ports:
	@echo "Checking required ports..."
	@echo "Port 5433 (PostgreSQL - Docker):"
	@lsof -i :5433 2>/dev/null && echo "  ❌ IN USE" || echo "  ✅ Available"
	@echo "Port 6379 (Redis):"
	@lsof -i :6379 2>/dev/null && echo "  ❌ IN USE" || echo "  ✅ Available"
	@echo "Port 9000 (MinIO API):"
	@lsof -i :9000 2>/dev/null && echo "  ❌ IN USE" || echo "  ✅ Available"
	@echo "Port 9001 (MinIO Console):"
	@lsof -i :9001 2>/dev/null && echo "  ❌ IN USE" || echo "  ✅ Available"

up:
	@echo "Starting docker-compose services..."
	@echo "Checking Docker daemon..."
	@docker info > /dev/null 2>&1 || (echo "ERROR: Docker daemon is not running. Please start Docker Desktop and try again." && exit 1)
	@echo "Checking for port conflicts..."
	@lsof -i :5433 > /dev/null 2>&1 && (echo "WARNING: Port 5433 is already in use. PostgreSQL may already be running." && echo "Run 'make check-ports' or 'lsof -i :5433' to see what's using it.") || true
	@lsof -i :6379 > /dev/null 2>&1 && (echo "WARNING: Port 6379 is already in use. Redis may already be running." && echo "Run 'make check-ports' or 'lsof -i :6379' to see what's using it.") || true
	@lsof -i :9000 > /dev/null 2>&1 && (echo "WARNING: Port 9000 is already in use. MinIO may already be running." && echo "Run 'make check-ports' or 'lsof -i :9000' to see what's using it.") || true
	@which docker-compose > /dev/null 2>&1 && docker-compose up -d || docker compose up -d
	@echo "Waiting for services to be ready..."
	@sleep 5
	@echo "Services started."
	@echo "  MinIO console: http://localhost:9001"
	@echo "  pgAdmin: http://localhost:5050 (may take 15-30 sec to become ready)"

down:
	@echo "Stopping docker-compose services..."
	@which docker-compose > /dev/null 2>&1 && docker-compose down || docker compose down

migrate:
	@if [ ! -d "venv" ]; then \
		echo "ERROR: Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	@echo "Running database migrations..."
	venv/bin/alembic upgrade head

migrate-create:
	@echo "Creating new migration..."
	@echo "Enter migration message:"; \
	read msg; \
	alembic revision --autogenerate -m "$$msg"

worker:
	@if [ ! -d "venv" ]; then \
		echo "ERROR: Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	@echo "Starting RQ worker..."
	@# macOS: avoid fork() crash (objc_initializeAfterForkError) when RQ forks work-horse
	@# NO_PROXY=* prevents proxy lookups that trigger Obj-C; OBJC_* fallback if needed
	@# Repo root on PYTHONPATH so worker can import apps.api.worker.render_stage from Redis job
	@cd apps/worker && \
		NO_PROXY='*' OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES \
		PYTHONPATH=$$(pwd)/../..:$$(pwd)/..:$$PYTHONPATH \
		$$(pwd)/../../venv/bin/python worker.py

api:
	@if [ ! -d "venv" ]; then \
		echo "ERROR: Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	@echo "Starting FastAPI server..."
	@PYTHONPATH=$$(pwd):$$PYTHONPATH venv/bin/uvicorn apps.api.main:app --reload --host 0.0.0.0 --port 8000

test:
	@if [ ! -d "venv" ]; then \
		echo "ERROR: Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	@echo "Running tests..."
	@PYTHONPATH=$$(pwd):$$(pwd)/packages/core:$$PYTHONPATH venv/bin/pytest apps/api/tests/ packages/core/tests/ -v

lint:
	@if [ ! -d "venv" ]; then \
		echo "ERROR: Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	@echo "Running linters..."
	venv/bin/black --check apps/ alembic/
	venv/bin/flake8 apps/ alembic/ --max-line-length=100 --exclude=__pycache__,*.pyc

lint-fix:
	@if [ ! -d "venv" ]; then \
		echo "ERROR: Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	@echo "Fixing linting issues..."
	venv/bin/black apps/ alembic/

test-redis:
	@echo "Testing Redis connection..."
	@which docker-compose > /dev/null 2>&1 && docker-compose exec -T redis redis-cli ping || docker compose exec -T redis redis-cli ping

F ?= sample_connectors.pptx
P ?= draft
O ?= ./output

run:
	@if [ ! -d "venv" ]; then \
		echo "ERROR: Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	@PYTHONPATH=$$(pwd):$$(pwd)/packages/core venv/bin/python scripts/slidesherlock_cli.py run "$(F)" --preset "$(P)" --output "$(O)"

demo:
	@if [ ! -d "venv" ]; then \
		echo "ERROR: Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	@echo "Running end-to-end demo (sample PPTX -> final.mp4)..."
	@echo "Requires: make up, make migrate (Postgres, Redis, MinIO running)."
	@PYTHONPATH=$$(pwd):$$(pwd)/packages/core venv/bin/python scripts/run_demo.py

clean:
	@echo "Cleaning build artifacts..."
	find . -type d -name __pycache__ -exec rm -r {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name "*.egg-info" -exec rm -r {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -r {} + 2>/dev/null || true
	@echo "Removing virtual environment..."
	@rm -rf venv
	@echo "Clean complete!"