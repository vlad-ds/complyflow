# Golden Dataset Verification Task

You are an independent QA reviewer. Your job is to verify the accuracy of a golden truth dataset that will be used to evaluate a RAG (Retrieval-Augmented Generation) system for regulatory documents.

## Files Location

- **Golden Dataset**: `output/regwatch/golden_dataset.json`
- **Source Documents**: `output/regwatch/cache/` (organized by regulation: `DORA/`, `MiCA/`)

## Your Task

For each of the 20 entries in `golden_dataset.json`, perform the following checks:

### 1. Quote Verification (Automated)
Confirm that `target_quote` exists **verbatim** in the `source_file`. This is a string match - the exact characters must appear in the document.

### 2. Question-Answer Alignment (Manual Review)
For each entry, read the surrounding context in the source document and verify:
- Does the `question` accurately reflect what someone would ask to find this information?
- Does the `ground_truth_answer` correctly and completely answer the question based on the `target_quote`?
- Is the `segment_id` (Article reference) accurate?

### 3. Answer Completeness Check
- Is the `ground_truth_answer` a fair summary of the `target_quote`?
- Does it capture the key information without adding facts not in the quote?
- Is anything important from the quote missing in the answer?

### 4. Question Quality Check
- Is the question specific enough that it could only be answered by this quote (not multiple places)?
- Is the question phrased naturally, as a user might actually ask it?
- Does the question avoid leading language that gives away the answer?

## Output Format

Create a verification report with this structure:

```markdown
# Golden Dataset Verification Report

## Summary
- Total entries: 20
- Quote matches: X/20
- Question-answer alignment issues: X
- Answer completeness issues: X
- Question quality issues: X

## Detailed Findings

### Entry 1: [source_file] - [segment_id]
- **Quote Match**: ✓ / ✗
- **Q&A Alignment**: ✓ / ✗ - [explanation if issue]
- **Answer Complete**: ✓ / ✗ - [explanation if issue]
- **Question Quality**: ✓ / ✗ - [explanation if issue]

[Repeat for all 20 entries]

## Recommended Fixes
[List any entries that need correction with specific suggestions]
```

## Important Notes

1. **Be thorough but fair** - Minor wording differences in answers are acceptable if the meaning is preserved
2. **Check Unicode characters** - The documents use curly quotes (`'` and `'`) not straight quotes (`'`)
3. **Context matters** - Read at least a paragraph around each quote to understand if the Q&A makes sense
4. **Flag ambiguity** - If a question could reasonably be answered by multiple passages, note this

## Start

Begin by reading the golden dataset, then systematically verify each entry against its source document. Report your findings in the format above.
