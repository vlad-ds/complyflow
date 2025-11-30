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

## agreement_date

The date when the contract was SIGNED or MADE (not when it takes effect).
- Different date formats are acceptable (e.g., "January 1, 1998" = "1998-01-01")
- Both should be empty if the contract has placeholder dates like "[•]" or "____"
- The signing date from signature blocks or "made as of" clauses

## effective_date

The date when the contract TAKES EFFECT.
- Different date formats are acceptable
- Often the same as agreement_date, but may differ
- Both should be empty if the contract has placeholder dates
- "Effective Date" as defined in the contract

## governing_law

The jurisdiction whose laws govern the contract.
- Normalize to jurisdiction name: "Florida" = "State of Florida" = "laws of Florida"
- Country-level is acceptable for international contracts
- Empty if no governing law clause exists
