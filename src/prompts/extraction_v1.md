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
- raw_snippet: Copy the exact notice requirement text, or null if not found
- reasoning: How you identified this (or why it's not found)
- normalized_value: Standardized period (e.g., "90 days") or null

### expiration_date
- raw_snippet: Copy the exact expiration/term text, or null if not found
- reasoning: How you determined the date (if relative, explain the calculation)
- normalized_value: ISO date (YYYY-MM-DD) if you can compute it, or describe the relative term if not (e.g., "2 years from Effective Date"). Return null if not specified.

### renewal_term
- raw_snippet: Copy the exact renewal text, or null if not found
- reasoning: How you identified this (or why it's not found)
- normalized_value: Standardized term (e.g., "1 year auto-renewal") or null

IMPORTANT: For expiration_date, if the date is relative (like "5 years from Effective Date"), compute it if you have the reference date, otherwise describe the relative term.
