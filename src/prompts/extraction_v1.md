Analyze this contract and extract the following information.

For each field, provide:
1. **raw_snippet**: The EXACT text copied verbatim from the document. Do not paraphrase or summarize - copy the relevant text character-for-character.
2. **reasoning**: Brief explanation of how you interpreted this
3. **normalized_value**: The processed/cleaned value

## Fields to Extract

### parties
- raw_snippet: Copy the exact text identifying the parties
- reasoning: How you identified the main parties
- normalized_value: List of party names (just company/person names, not definitions like "Licensor")

### contract_type
- raw_snippet: Copy the exact title or description indicating contract type
- reasoning: Why this classification
- normalized_value: Must be one of: {contract_types}

### notice_period
- raw_snippet: Copy the exact notice requirement text, or empty string if not found
- reasoning: How you identified this (or why it's not found)
- normalized_value: Standardized period (e.g., "90 days") or empty string if not found
- IMPORTANT: Only extract GENERAL notice periods that apply to standard termination or non-renewal. Do NOT extract contextual or conditional notice periods that only apply in specific circumstances (e.g., notice periods tied to other agreements terminating).

### expiration_date
- raw_snippet: Copy the exact expiration/term text, or empty string if not found
- reasoning: How you determined the date (if relative, explain the calculation)
- normalized_value: One of the following:
  - ISO date (YYYY-MM-DD) if you can compute a specific date
  - "perpetual" if the agreement continues indefinitely/in perpetuity
  - A description of the relative term if you cannot compute (e.g., "2 years from Effective Date")
  - Empty string if not specified

### renewal_term
- raw_snippet: Copy the exact renewal text, or empty string if not found
- reasoning: How you identified this (or why it's not found)
- normalized_value: Standardized term (e.g., "1 year auto-renewal") or empty string if not found
