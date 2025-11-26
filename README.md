# ComplyFlow

AI-powered legal and compliance platform for automated contract management and regulatory monitoring.

## Setup

1. Install dependencies using [uv](https://docs.astral.sh/uv/):

```bash
uv sync
```

2. Copy the environment file and add your API keys:

```bash
cp .env.example .env
```

Required API keys:
- `ANTHROPIC_API_KEY` - For Anthropic token counting
- `GOOGLE_API_KEY` - For Gemini token counting

## Usage

```bash
# Run scripts
uv run python script.py
```

## Project Structure

```
src/
  extraction/     # PDF text extraction, metadata extraction
  utils/          # Token counting utilities
cuad/             # Test contracts from CUAD dataset
```

## Test Data

The `cuad/` directory contains sample contracts from the CUAD dataset with ground truth labels for validating extraction accuracy.
