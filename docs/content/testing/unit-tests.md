---
id: unit-tests
title: Unit Tests
sidebar_position: 1
---

# Unit Tests

SlideSherlock has an extensive test suite covering all core pipeline modules. Tests live in `packages/core/tests/` and `apps/api/tests/`.

---

## Running All Tests

```bash
make test
```

Internally runs:

```bash
PYTHONPATH=$(pwd):$(pwd)/packages/core:$PYTHONPATH \
  venv/bin/pytest apps/api/tests/ packages/core/tests/ -v
```

---

## Running a Specific Test File

```bash
PYTHONPATH=$(pwd):$(pwd)/packages/core \
  venv/bin/pytest packages/core/tests/test_verifier.py -v
```

## Running a Specific Test Case

```bash
PYTHONPATH=$(pwd):$(pwd)/packages/core \
  venv/bin/pytest packages/core/tests/test_verifier.py::test_pass_segment -v
```

## Running Tests with Output

```bash
PYTHONPATH=$(pwd):$(pwd)/packages/core \
  venv/bin/pytest packages/core/tests/ -v -s
```

## Running Tests Matching a Pattern

```bash
PYTHONPATH=$(pwd):$(pwd)/packages/core \
  venv/bin/pytest packages/core/tests/ -k "evidence" -v
```

---

## Test Coverage

```bash
PYTHONPATH=$(pwd):$(pwd)/packages/core \
  venv/bin/pytest packages/core/tests/ \
  --cov=packages/core \
  --cov-report=html \
  --cov-report=term-missing
```

Open the HTML report:
```bash
open htmlcov/index.html
```

---

## Test Modules

| Test File | Module Under Test | Key Scenarios |
|---|---|---|
| `test_verifier.py` | `verifier.py` | PASS/REWRITE/REMOVE verdicts, image claim enforcement, hedging, rewrite loop |
| `test_evidence_index.py` (via integration) | `evidence_index.py` | Stable evidence IDs, notes/shapes/connectors extraction |
| `test_script_context.py` | `script_context.py` | Context bundle construction, phrasing policy |
| `test_script_plan.py` | `explain_plan.py` | Plan generation, section types |
| `test_merge_engine.py` | `merge_engine.py` | Graph merging, provenance tracking, confidence propagation |
| `test_narration_blueprint.py` | `narration_blueprint.py` | Slide type classification, template narration |
| `test_narration_source.py` | `narration_source.py` | Narration source selection |
| `test_audio_prepare.py` | `audio_prepare.py` | Audio mode selection, narration priority |
| `test_timeline_alignment.py` | `alignment.py` | Timestamp mapping |
| `test_image_classifier.py` | `image_classifier.py` | PHOTO/DIAGRAM/CHART classification |
| `test_image_extract.py` | `image_extract.py` | Image extraction, stable image IDs |
| `test_image_understand.py` | `image_understand.py` | Evidence cross-linking |
| `test_image_evidence_integration.py` | Integration | Image evidence pipeline |
| `test_photo_understand.py` | `photo_understand.py` | Vision provider integration |
| `test_diagram_understand.py` | `diagram_understand.py` | Diagram entity extraction |
| `test_slide_caption_fallback.py` | `slide_caption_fallback.py` | Fallback caption generation |
| `test_doctor.py` | `doctor.py` | Dependency detection |
| `test_presets.py` | `presets.py` | Preset variable application |
| `test_variants.py` | `variants.py` | Variant list generation |
| `test_translation.py` | `translation.py` | Script translation |
| `test_notes_config.py` | `notes_config.py` | On-screen notes configuration |
| `test_on_screen_notes.py` | On-screen notes rendering | Notes overlay |
| `test_video_config.py` | `video_config.py` | Video configuration loading |
| `test_subtitle_generator.py` | `subtitle_generator.py` | SRT generation |
| `test_vision_provider_openai.py` | `vision_provider_openai.py` | OpenAI vision provider |
| `test_vision_day3_integration.py` | Vision pipeline | End-to-end vision integration |

---

## Writing Tests

Tests use the built-in `pytest` framework. The stub providers make unit tests fully self-contained — no external services required.

```python
# packages/core/tests/test_my_module.py
import pytest
from my_module import my_function
from llm_provider import StubLLMProvider
from vision_provider import StubVisionProvider

def test_basic_scenario():
    stub_llm = StubLLMProvider()
    result = my_function(input_data, llm_provider=stub_llm)
    assert result.status == "expected"

def test_edge_case():
    with pytest.raises(ValueError, match="Expected error message"):
        my_function(invalid_input)
```

### Using Fixtures

Common fixtures are available for evidence index, parsed slides, and graph data:

```python
@pytest.fixture
def sample_slide_data():
    return {
        "slide_index": 0,
        "slide_text": "Architecture Overview",
        "notes": "This slide shows the three-tier architecture.",
        "shapes": [
            {"ppt_shape_id": "sp_1", "bbox": {...}, "text_runs": ["Web Tier"]}
        ],
        "connectors": []
    }

def test_evidence_index(sample_slide_data):
    # Uses the fixture
    ...
```

---

## Linting

```bash
# Check code style (black + flake8)
make lint

# Auto-fix formatting
make lint-fix
```

flake8 configuration: max line length 100, excludes `__pycache__` and `.pyc` files.
