You are evaluating whether an AI model's extraction matches the ground truth from a legal contract.

## Field: {field}

{field_guidance}

## Ground Truth (from human annotators)
{ground_truth}

## Model Output
{model_output}

## Task
Determine if the MODEL OUTPUT correctly captures the same information as the GROUND TRUTH.

Respond with ONLY a JSON object (no markdown code blocks):
{{"judgment": "MATCH" or "NO_MATCH", "reasoning": "brief explanation"}}
