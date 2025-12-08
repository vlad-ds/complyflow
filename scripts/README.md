# Scripts

> **Note**: Many of these scripts are ad-hoc utilities developed during the project. As future work, the evaluation and indexing scripts should be integrated into stable modules within `src/` with proper CLI interfaces and test coverage.

## Regwatch Evaluation

Scripts for evaluating the regulatory monitoring RAG pipeline. These were used to generate metrics for the project report.

| Script | Description |
|--------|-------------|
| `eval_endpoint.py` | Tests the production `/regwatch/chat` endpoint against a golden dataset, runs LLM-as-judge scoring |
| `eval_generation.py` | Runs 4 LLMs (GPT-5-mini, GPT-5.1, Command-R, Gemini Flash) on golden dataset with Langfuse cost tracking |
| `eval_judge.py` | Uses Gemini Flash as an impartial judge to score responses on correctness and citation formatting |
| `eval_retrieval.py` | Tests RAG retrieval using FastEmbed embeddings and in-memory Qdrant |
| `eval_snowflake_arctic.py` | Evaluates Snowflake Arctic embeddings against the golden dataset using Qdrant Cloud |

**Prerequisites**: These scripts depend on files in `output/regwatch/` (golden dataset, cached documents) which are gitignored.

## Regwatch Operations

| Script | Description |
|--------|-------------|
| `index_regwatch.py` | Indexes regulatory documents from local cache to Qdrant Cloud |
| `reindex_all.py` | Re-indexes all cached documents with updated metadata headers. Supports `--dry-run` |

## Contract API Testing

| Script | Description |
|--------|-------------|
| `test_api.py` | Tests the contract intake API: PDF text extraction and full extraction pipeline |

## Development / Debugging

Ad-hoc scripts for testing specific components during development.

| Script | Description |
|--------|-------------|
| `test_cellar.py` | Tests Cellar API for fetching EUR-Lex full text |
| `test_chunk_integrity.py` | Evaluates chunking strategies (512/1024/2048 chars) for sentence preservation |
| `test_langfuse_pricing.py` | Verifies Langfuse tracks pricing correctly for each LLM provider |
| `test_regwatch.py` | Tests EUR-Lex RSS connector with Jina.ai full text fetching |

## Usage

All scripts should be run from the project root with `PYTHONPATH=src`:

```bash
PYTHONPATH=src uv run python scripts/<script_name>.py
```
