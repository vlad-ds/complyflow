# Contract Extraction Evaluation

This document describes the evaluation methodology and results for our multi-model contract metadata extraction system.

## Evaluation Overview

We evaluated 4 models across 3 providers on a 10-contract training set from the CUAD dataset:

| Model | Provider | Model ID |
|-------|----------|----------|
| sonnet | Anthropic | claude-sonnet-4-5-20250929 |
| gpt-5 | OpenAI | gpt-5 |
| gpt-5-mini | OpenAI | gpt-5-mini |
| flash | Google | gemini-2.0-flash |

### Fields Evaluated

5 fields matching CUAD ground truth:
- `parties` - Legal entity names
- `contract_type` - One of 26 CUAD contract types
- `notice_period` - Notice period to terminate renewal
- `expiration_date` - Contract expiration/term
- `renewal_term` - Auto-renewal terms

## Evaluation Methodology

### LLM-as-Judge Approach

We use Gemini Flash as an LLM judge to compare model extractions against CUAD ground truth. This approach handles semantic equivalence (e.g., "90 days" = "three months") that exact string matching would miss.

**Key design decisions:**

1. **Programmatic empty handling**: Flash struggled to correctly identify empty values, so we handle empty-vs-empty and empty-vs-non-empty comparisons programmatically before calling the LLM.

2. **Exact match for contract_type**: Since contract_type must match one of 26 predefined categories, we use case-insensitive exact string matching.

3. **Field-specific guidance**: The judge prompt includes tailored guidance for each field (e.g., for parties: ignore aliases and role labels, focus on legal entity names).

4. **Structured output**: We use Pydantic models with JSON schema to ensure reliable parsing of judge responses.

### Prompt Files

- `prompts/extraction_v1.md` - Extraction prompt with field definitions
- `prompts/judge_v1.md` - Judge prompt template
- `prompts/judge_field_guidance.md` - Field-specific judging guidance

## Results Summary

### Overall Accuracy

| Model | Accuracy | Match | No Match | Error |
|-------|----------|-------|----------|-------|
| gpt-5-mini | **90.0%** | 45 | 5 | 0 |
| flash | 88.0% | 44 | 6 | 0 |
| gpt-5 | 88.0% | 44 | 6 | 0 |
| sonnet | 84.0% | 42 | 8 | 0 |

### Field-Level Accuracy

| Field | Accuracy | Match | No Match |
|-------|----------|-------|----------|
| parties | **100%** | 40 | 0 |
| renewal_term | 92.5% | 37 | 3 |
| notice_period | 90.0% | 36 | 4 |
| expiration_date | 80.0% | 32 | 8 |
| contract_type | 75.0% | 30 | 10 |

### Cost vs Performance

| Model | Accuracy | Cost (10 contracts) | Cost per Contract | Avg Latency |
|-------|----------|---------------------|-------------------|-------------|
| gpt-5-mini | 90.0% | $0.09 | **$0.009** | 31.5s |
| flash | 88.0% | $0.11 | $0.011 | **10.5s** |
| gpt-5 | 88.0% | $0.53 | $0.053 | 68.9s |
| sonnet | 84.0% | $0.83 | $0.083 | 25.4s |

**Key finding:** GPT-5-mini delivers the best accuracy (90%) at the lowest cost ($0.009/contract). Flash is the fastest option (10.5s) with comparable accuracy (88%) and cost ($0.011/contract).

## Error Analysis

### Contract Type (75% accuracy)

All 10 errors concentrate in 3 contracts where ALL models disagree with CUAD labels:

| Contract | Model Output (all agree) | CUAD Label |
|----------|-------------------------|------------|
| 01_service_gpaq.pdf | Sponsorship Agreement | Service Agreement |
| 04_service_integrity.pdf | Distributor Agreement | Service Agreement |
| 10_outsourcing_paratek.pdf | Manufacturing/Supply Agreement | Outsourcing Agreement |

These appear to be CUAD labeling issues rather than model errors - the models analyze contract substance while CUAD may have used filename conventions.

### Expiration Date (80% accuracy)

Errors fall into two categories:

1. **Redacted contracts** (5 errors): Contracts 09 and 10 contain `[* * *]` redactions. Models correctly return empty since no usable date exists, but CUAD ground truth includes the full clause with redactions.

2. **Complex conditional terms** (2 errors): Contract 03 has termination conditions tied to debt obligations that are difficult to summarize.

3. **Misread term** (1 error): Flash read "24 months" instead of "12 months" in Contract 02.

### Prompt Improvements Made

1. **Expiration date**: Updated prompt to preserve relative terms (e.g., "5 years from Effective Date") rather than computing specific dates. CUAD ground truth uses relative terms.

2. **Contract type**: Added guidance to analyze contract substance, not just titles.

3. **Notice period**: Clarified that this is specifically for "Notice Period to Terminate Renewal" - the advance notice required to prevent automatic renewal.

## Evaluation Commands

```bash
# Run extractions (idempotent - skips existing)
python -m evaluation extract --models flash

# Generate comparison report (queries Langfuse for costs)
python -m evaluation report

# Create eval pairs (after extractions complete)
python -m evaluation pairs

# Run LLM-as-judge evaluation
python -m evaluation judge

# Force re-extraction
python -m evaluation extract --models flash --force
```

## Langfuse Integration

All extractions and judge calls are traced in Langfuse with eval_id tags for cost tracking:
- Extraction: `eval_{model}_{timestamp}_{uuid}`
- Judge: `judge_{timestamp}_{uuid}`

The report command fetches costs from Langfuse API with retry logic (exponential backoff) to handle rate limits.

## Output Files

```
output/
├── anthropic/           # Sonnet extraction results
├── gemini/              # Flash extraction results
├── openai/              # GPT-5, GPT-5-mini results
├── eval_pairs/          # Paired ground truth + model outputs
├── judge_results/       # Judge evaluation outputs
│   ├── *_summary.json   # Aggregated metrics
│   ├── *_details.json   # Full judgment details
│   └── *.csv            # Human-readable results
└── run_summaries/       # Cost/latency comparison reports
```

## Recommendations

1. **Production model**: GPT-5-mini offers the best accuracy/cost ratio at $0.009/contract.

2. **Speed-critical**: Gemini Flash at 10.5s/contract is 3x faster than others with 88% accuracy.

3. **Contract type handling**: Consider using an ensemble approach or adding a verification step for contract types, as models consistently disagree with some CUAD labels.

4. **Redacted contracts**: Flag contracts with `[* * *]` redactions for manual review rather than attempting extraction.

## Next Steps

1. Run final evaluation on test set (10 additional contracts)
2. Build confidence scoring based on raw_snippet presence
3. Add human-in-the-loop review for low-confidence extractions
