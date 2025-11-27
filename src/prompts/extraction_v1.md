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
- IMPORTANT: This field is specifically for "Notice Period to Terminate Renewal" - the advance notice required to PREVENT automatic renewal. Do NOT extract:
  - General termination notice periods (notice to terminate the agreement at will)
  - Conditional notice periods tied to specific circumstances
  - Notice periods for breach/cause termination
- If the contract auto-renews unless a party gives notice (e.g., "90 days before expiration"), extract that period.
- If the contract requires Board approval for renewal (rather than notice to prevent it), the notice_period is empty.

### expiration_date
- raw_snippet: Copy the exact expiration/term text, or empty string if not found
- reasoning: How you determined the date (if relative, explain the calculation)
- normalized_value: One of the following:
  - ISO date (YYYY-MM-DD) if you can compute a specific date
  - "perpetual" ONLY if the agreement explicitly states it continues "in perpetuity", "indefinitely", or similar language
  - A description of the relative term if you cannot compute (e.g., "2 years from Effective Date")
  - Empty string if the contract is silent on term/expiration (even if it can be terminated at will)
- IMPORTANT: Do NOT infer "perpetual" just because the contract lacks an expiration date or can be terminated at any time. "Perpetual" requires explicit language in the contract.

### renewal_term
- raw_snippet: Copy the exact renewal text, or empty string if not found
- reasoning: How you identified this (or why it's not found)
- normalized_value: Standardized term (e.g., "1 year auto-renewal") or empty string if not found
