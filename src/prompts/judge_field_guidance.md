# Field-Specific Guidance for LLM Judge

## parties

Focus on the LEGAL ENTITY NAMES (e.g., "HOF Village, LLC", "Constellation NewEnergy, Inc.")
- IGNORE shorthand aliases like "HOFV", "PFHOF", "Constellation" - these are just abbreviations
- IGNORE role labels like "Licensor", "Licensee", "Seller", "Buyer" - these are not party names
- IGNORE descriptive text like "on behalf of itself and its retail affiliates"
- A MATCH means the model captured the same actual legal entities, even if it excluded aliases/roles
- Minor formatting differences are acceptable (e.g., "Inc." vs "Inc", including or omitting "d/b/a" names)

## expiration_date

The model output should capture the SAME expiration date/term as the ground truth.
- Different formats are acceptable (e.g., "December 31, 2028" = "2028-12-31")
- Summaries are acceptable if they capture the key information (e.g., "12 months from Commencement Date")
- "perpetual" matches "in perpetuity" or "continues indefinitely"

## notice_period

This is the advance notice required to PREVENT automatic renewal.
- "90 days" = "ninety (90) days" = "90 day notice"
- The time period must match semantically

## renewal_term

This describes how/whether the contract renews.
- Summaries are acceptable if they capture the key aspects (auto-renewal, duration, conditions)
- "1 year auto-renewal" captures the essence of verbose renewal language
