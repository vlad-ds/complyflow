# Frontend: Contract Editor with Citations

## What Changed

We added a new **Citations** table in Airtable that stores, for each extracted field:
- **quote**: The exact text from the PDF that the AI used
- **reasoning**: Why the AI interpreted it that way
- **ai_value**: The AI's original extracted value

This is separate from the **Contracts** table which holds the current (possibly human-edited) values.

## New API Endpoint

```
GET /contracts/{id}/citations
```

Returns one citation per field with `field_name`, `quote`, `reasoning`, and `ai_value`.

## Desired UI

In the contract editing view, display each field as a row with:

1. **Quote from PDF** - the exact source text (collapsible)
2. **AI Reasoning** - explanation of the interpretation (collapsible)
3. **AI Value** - what the AI originally extracted
4. **Current Value** - the editable field (may differ if human edited)

If the current value differs from the AI value, show a visual indicator that the field has been edited.

The goal is to let reviewers see *why* the AI extracted each value, compare it to the source text, and make informed corrections when needed.
