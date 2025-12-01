"""OpenAI Assistants API provider with Code Interpreter for date computation.

Uses the Assistants API with code_interpreter tool for precise date arithmetic.

Requires environment variables:
- OPENAI_API_KEY: Your OpenAI API key
- LANGFUSE_PUBLIC_KEY: Your Langfuse public key (for tracing)
- LANGFUSE_SECRET_KEY: Your Langfuse secret key (for tracing)
"""

import json
import time
from dataclasses import dataclass
from typing import Any

from langfuse import get_client, observe
from openai import OpenAI
from opentelemetry.instrumentation.openai import OpenAIInstrumentor

# Initialize instrumentation once at module load
_instrumentor = OpenAIInstrumentor()
if not _instrumentor.is_instrumented_by_opentelemetry:
    _instrumentor.instrument()


@dataclass
class DateComputationResponse:
    """Response from date computation."""

    content: dict  # The computed dates
    model: str
    input_tokens: int
    output_tokens: int
    latency_seconds: float
    code_interpreter_used: bool
    raw_response: Any = None


class OpenAIAssistantsProvider:
    """OpenAI Assistants provider with Code Interpreter for date computation."""

    provider_name = "openai-assistants"

    MODELS = {
        "gpt-5-mini": "gpt-5-mini-2025-08-07",
        "gpt-5": "gpt-5-2025-08-07",
        "gpt-4o": "gpt-4o-2024-08-06",
        "gpt-4o-mini": "gpt-4o-mini-2024-07-18",
    }

    def __init__(self, model: str = "gpt-4o"):
        """Initialize the Assistants provider.

        Args:
            model: Model to use. Defaults to "gpt-4o" (Assistants API has limited model support).
                   Note: gpt-5 series not yet supported by Assistants API.
        """
        self._client = OpenAI()
        # Force gpt-4o for Assistants API since gpt-5 series isn't supported yet
        if "gpt-5" in model:
            print(f"Note: {model} not supported by Assistants API, using gpt-4o instead")
            model = "gpt-4o"
        self._model = self._resolve_model(model)
        self._assistant_id: str | None = None

    def _resolve_model(self, model: str) -> str:
        """Resolve short model name to full model ID."""
        return self.MODELS.get(model, model)

    def _create_assistant(self, instructions: str) -> str:
        """Create an assistant with code interpreter enabled.

        Args:
            instructions: System instructions for the assistant.

        Returns:
            Assistant ID.
        """
        assistant = self._client.beta.assistants.create(
            name="Date Computation Assistant",
            instructions=instructions,
            model=self._model,
            tools=[{"type": "code_interpreter"}],
        )
        self._assistant_id = assistant.id
        return assistant.id

    def _delete_assistant(self) -> None:
        """Delete the assistant after use."""
        if self._assistant_id:
            self._client.beta.assistants.delete(self._assistant_id)
            self._assistant_id = None

    @observe(name="date-computation-assistants")
    def compute_dates(
        self,
        prompt: str,
        contract_data: dict,
        tags: list[str] | None = None,
    ) -> DateComputationResponse:
        """Compute dates using the Assistants API with code interpreter.

        Args:
            prompt: The date computation prompt template.
            contract_data: Dict with agreement_date, effective_date, expiration_date fields.
            tags: Optional Langfuse tags for tracking.

        Returns:
            DateComputationResponse with computed dates and usage metadata.
        """
        start_time = time.time()

        # Update Langfuse trace with tags
        langfuse = get_client()
        base_tags = ["date-computation", "code-interpreter:true"]
        all_tags = base_tags + (tags or [])
        langfuse.update_current_trace(
            name="date-computation-assistants",
            tags=all_tags,
            metadata={
                "model": self._model,
                "provider": self.provider_name,
                "code_interpreter": True,
            },
        )

        # Format the prompt with contract data
        contract_data_str = json.dumps(contract_data, indent=2)
        full_prompt = prompt.format(contract_data=contract_data_str)

        # Create assistant
        assistant_id = self._create_assistant(
            "You are a date computation assistant. Use Python code to compute dates precisely. "
            "Always use the code interpreter to verify date calculations."
        )

        try:
            # Create thread and message
            thread = self._client.beta.threads.create()
            self._client.beta.threads.messages.create(
                thread_id=thread.id,
                role="user",
                content=full_prompt,
            )

            # Run the assistant
            run = self._client.beta.threads.runs.create_and_poll(
                thread_id=thread.id,
                assistant_id=assistant_id,
            )

            if run.status != "completed":
                raise RuntimeError(f"Assistant run failed with status: {run.status}")

            # Get the response
            messages = self._client.beta.threads.messages.list(thread_id=thread.id)
            assistant_message = next(
                msg for msg in messages.data if msg.role == "assistant"
            )

            # Extract text content
            response_text = ""
            for content_block in assistant_message.content:
                if content_block.type == "text":
                    response_text = content_block.text.value
                    break

            # Parse JSON from response (handle markdown code blocks)
            json_str = response_text.strip()

            # Try to extract JSON from markdown code blocks
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0].strip()
            elif "```" in json_str:
                # Find content between first ``` and next ```
                parts = json_str.split("```")
                if len(parts) >= 2:
                    json_str = parts[1].strip()
                    # Remove language identifier if present
                    if json_str and json_str.split('\n')[0].isalpha():
                        json_str = '\n'.join(json_str.split('\n')[1:])

            # Try to find JSON object in the response
            if not json_str.startswith('{'):
                # Look for JSON object in the text
                start_idx = response_text.find('{')
                if start_idx != -1:
                    # Find matching closing brace
                    depth = 0
                    for i, char in enumerate(response_text[start_idx:]):
                        if char == '{':
                            depth += 1
                        elif char == '}':
                            depth -= 1
                            if depth == 0:
                                json_str = response_text[start_idx:start_idx + i + 1]
                                break

            try:
                computed_dates = json.loads(json_str)
            except json.JSONDecodeError as e:
                raise ValueError(f"Failed to parse JSON from response: {response_text[:200]}...") from e

            # Check if code interpreter was used
            run_steps = self._client.beta.threads.runs.steps.list(
                thread_id=thread.id,
                run_id=run.id,
            )
            code_interpreter_used = any(
                step.type == "tool_calls"
                and any(
                    tc.type == "code_interpreter" for tc in (step.step_details.tool_calls or [])
                )
                for step in run_steps.data
                if hasattr(step.step_details, "tool_calls")
            )

            latency = time.time() - start_time

            # Clean up
            self._client.beta.threads.delete(thread.id)

            return DateComputationResponse(
                content=computed_dates,
                model=self._model,
                input_tokens=run.usage.prompt_tokens if run.usage else 0,
                output_tokens=run.usage.completion_tokens if run.usage else 0,
                latency_seconds=latency,
                code_interpreter_used=code_interpreter_used,
                raw_response=run,
            )

        finally:
            self._delete_assistant()

    def get_langfuse_session_name(self, base_name: str = "date-computation") -> str:
        """Get Langfuse session name with provider suffix."""
        return f"{base_name}-{self.provider_name}"
