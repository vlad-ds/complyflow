# Multi-Model Extraction Architecture

This document describes the modular multi-provider extraction system for contract metadata extraction.

## Overview

The system supports extracting contract metadata using three LLM providers:
- **Anthropic** (Claude Sonnet 4.5, Opus, Haiku)
- **Google Gemini** (2.5 Flash, Flash-Lite, Pro)
- **OpenAI** (GPT-4.1, GPT-4.1-mini, GPT-4.1-nano)

All providers use structured JSON output to ensure reliable parsing.

## Directory Structure

```
output/
├── anthropic/          # Anthropic extraction results
├── gemini/             # Gemini extraction results
└── openai/             # OpenAI extraction results

cuad/
├── train/
│   ├── contracts/      # 10 training PDFs
│   ├── metadata.json   # Ground truth labels
│   └── metadata.csv
├── test/
│   └── contracts/      # Test set (to be added)
└── fake_data/

temp/extracted_text/
└── train/              # Pre-extracted text from training PDFs
```

## Provider Architecture

### Base Class (`src/llm/base.py`)

```python
class BaseLLMProvider(ABC):
    provider_name: str  # "anthropic", "openai", "gemini"

    @abstractmethod
    def extract_json(self, prompt, document, json_schema, model=None) -> LLMResponse:
        pass

    def get_langfuse_session_name(self, base_name="extraction-eval") -> str:
        return f"{base_name}-{self.provider_name}"
```

### Provider Implementations

| File | Provider | Default Model | Models Available |
|------|----------|---------------|------------------|
| `anthropic_provider.py` | Anthropic | `claude-sonnet-4-5-20250929` | sonnet, opus, haiku |
| `gemini_provider.py` | Google | `gemini-2.5-flash-preview-05-20` | flash, flash-lite, pro |
| `openai_provider.py` | OpenAI | `gpt-4.1-mini-2025-04-14` | gpt-4.1, gpt-4.1-mini, gpt-4.1-nano |

### Getting a Provider

```python
from llm import get_provider

# Default model
provider = get_provider("anthropic")

# Specific model
provider = get_provider("openai", model="gpt-4.1")
```

## Extraction Module

The extraction is provider-agnostic:

```python
from extraction import extract_contract_metadata
from llm import get_provider

provider = get_provider("gemini")
result = extract_contract_metadata(provider, "path/to/contract.txt")
```

## CLI Usage

```bash
# Default (Anthropic Sonnet)
python -m extraction.run_extraction temp/extracted_text/train/06_license_morganstanley.txt

# OpenAI GPT-4.1
python -m extraction.run_extraction temp/extracted_text/train/06_license_morganstanley.txt -p openai

# Gemini Flash
python -m extraction.run_extraction temp/extracted_text/train/06_license_morganstanley.txt -p gemini

# Specific model
python -m extraction.run_extraction temp/extracted_text/train/06_license_morganstanley.txt -p openai -m gpt-4.1-nano
```

Output is saved to `output/<provider>/<contract_name>_extraction.json`.

## Langfuse Tracing

Each provider's extractions are tracked with a session name pattern:
- `extraction-eval-anthropic`
- `extraction-eval-gemini`
- `extraction-eval-openai`

This allows cost and performance analysis per provider in the Langfuse dashboard.

## Required Environment Variables

```bash
# Anthropic
ANTHROPIC_API_KEY=...

# Google Gemini
GOOGLE_API_KEY=...

# OpenAI
OPENAI_API_KEY=...

# Langfuse (for tracing)
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
LANGFUSE_HOST=https://cloud.langfuse.com
```

## Extraction Results (Training Set)

Anthropic Claude Sonnet achieved **96% accuracy** (48/50 fields) on the 10-contract training set against CUAD ground truth.

The 2 mismatches were `contract_type` on hybrid agreements where both classifications are defensible:
- `01_service_gpaq`: Claude chose "Sponsorship Agreement", CUAD has "Service Agreement"
- `04_service_integrity`: Claude chose "Distributor Agreement", CUAD has "Service Agreement"

## Next Steps

1. Add 10 test contracts to `cuad/test/contracts/`
2. Run extraction with all three providers on train set
3. Compare accuracy and cost across providers
4. Run on test set for final evaluation
