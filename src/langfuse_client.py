"""Langfuse client for accessing traces, observations, and metrics.

Provides convenient methods to query Langfuse data for debugging,
analysis, and monitoring of LLM calls.

Requires environment variables:
- LANGFUSE_PUBLIC_KEY: Your Langfuse public key
- LANGFUSE_SECRET_KEY: Your Langfuse secret key
- LANGFUSE_BASE_URL: Langfuse host (e.g., https://cloud.langfuse.com)
"""

from datetime import datetime
from typing import Any

from dotenv import load_dotenv
from langfuse import Langfuse

load_dotenv()


def get_langfuse_client() -> Langfuse:
    """Get a Langfuse client for querying observability data.

    Returns:
        Langfuse client configured from environment variables.
    """
    return Langfuse()


def list_traces(
    limit: int = 20,
    user_id: str | None = None,
    session_id: str | None = None,
    name: str | None = None,
    tags: list[str] | None = None,
    from_timestamp: datetime | None = None,
    to_timestamp: datetime | None = None,
) -> list[dict[str, Any]]:
    """List traces with optional filtering.

    Args:
        limit: Maximum number of traces to return (default 20).
        user_id: Filter by user ID.
        session_id: Filter by session ID.
        name: Filter by trace name.
        tags: Filter by tags.
        from_timestamp: Filter traces after this time.
        to_timestamp: Filter traces before this time.

    Returns:
        List of trace dictionaries.
    """
    client = get_langfuse_client()
    kwargs: dict[str, Any] = {"limit": limit}

    if user_id:
        kwargs["user_id"] = user_id
    if session_id:
        kwargs["session_id"] = session_id
    if name:
        kwargs["name"] = name
    if tags:
        kwargs["tags"] = tags
    if from_timestamp:
        kwargs["from_timestamp"] = from_timestamp
    if to_timestamp:
        kwargs["to_timestamp"] = to_timestamp

    response = client.api.trace.list(**kwargs)
    return [trace.dict() for trace in response.data]


def get_trace(trace_id: str) -> dict[str, Any]:
    """Get a specific trace by ID.

    Args:
        trace_id: The trace ID to fetch.

    Returns:
        Trace dictionary with full details.
    """
    client = get_langfuse_client()
    trace = client.api.trace.get(trace_id)
    return trace.dict()


def list_observations(
    trace_id: str | None = None,
    name: str | None = None,
    obs_type: str | None = None,
    limit: int = 50,
    from_start_time: datetime | None = None,
    to_start_time: datetime | None = None,
) -> list[dict[str, Any]]:
    """List observations (spans/generations) with filtering.

    Args:
        trace_id: Filter by parent trace ID.
        name: Filter by observation name.
        obs_type: Filter by type (GENERATION, SPAN, EVENT).
        limit: Maximum number of observations (default 50).
        from_start_time: Filter observations after this time.
        to_start_time: Filter observations before this time.

    Returns:
        List of observation dictionaries.
    """
    client = get_langfuse_client()
    kwargs: dict[str, Any] = {"limit": limit}

    if trace_id:
        kwargs["trace_id"] = trace_id
    if name:
        kwargs["name"] = name
    if obs_type:
        kwargs["type"] = obs_type
    if from_start_time:
        kwargs["from_start_time"] = from_start_time
    if to_start_time:
        kwargs["to_start_time"] = to_start_time

    response = client.api.observations.get_many(**kwargs)
    return [obs.dict() for obs in response.data]


def get_observation(observation_id: str) -> dict[str, Any]:
    """Get a specific observation by ID.

    Args:
        observation_id: The observation ID to fetch.

    Returns:
        Observation dictionary with full details including input/output.
    """
    client = get_langfuse_client()
    obs = client.api.observations.get(observation_id)
    return obs.dict()


def list_sessions(limit: int = 20) -> list[dict[str, Any]]:
    """List sessions.

    Args:
        limit: Maximum number of sessions (default 20).

    Returns:
        List of session dictionaries.
    """
    client = get_langfuse_client()
    response = client.api.sessions.list(limit=limit)
    return [session.dict() for session in response.data]


def get_trace_summary(trace_id: str) -> dict[str, Any]:
    """Get a summary of a trace including its observations.

    Args:
        trace_id: The trace ID to summarize.

    Returns:
        Dictionary with trace metadata and observation summary.
    """
    trace = get_trace(trace_id)
    observations = list_observations(trace_id=trace_id)

    # Calculate totals
    total_tokens = 0
    total_cost = 0.0
    generations = []

    for obs in observations:
        if obs.get("type") == "GENERATION":
            usage = obs.get("usage") or {}
            input_tokens = usage.get("input", 0) or 0
            output_tokens = usage.get("output", 0) or 0
            obs_total = usage.get("total", input_tokens + output_tokens) or 0
            total_tokens += obs_total
            total_cost += obs.get("calculated_total_cost", 0) or 0
            generations.append({
                "name": obs.get("name"),
                "model": obs.get("model"),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "tokens": obs_total,
                "cost": obs.get("calculated_total_cost"),
                "latency_ms": obs.get("latency"),
            })

    return {
        "trace_id": trace_id,
        "name": trace.get("name"),
        "user_id": trace.get("user_id"),
        "session_id": trace.get("session_id"),
        "timestamp": trace.get("timestamp"),
        "tags": trace.get("tags"),
        "total_tokens": total_tokens,
        "total_cost": total_cost,
        "observation_count": len(observations),
        "generations": generations,
    }


def get_recent_activity(
    hours: int = 24,
    limit: int = 50,
) -> dict[str, Any]:
    """Get a summary of recent Langfuse activity.

    Args:
        hours: Look back this many hours (default 24).
        limit: Maximum traces to analyze (default 50).

    Returns:
        Dictionary with activity summary including trace count,
        total tokens, total cost, and model breakdown.
    """
    from_time = datetime.now().replace(
        hour=datetime.now().hour - hours if datetime.now().hour >= hours else 0
    )

    traces = list_traces(limit=limit, from_timestamp=from_time)

    total_tokens = 0
    total_cost = 0.0
    models: dict[str, int] = {}
    trace_names: dict[str, int] = {}

    for trace in traces:
        trace_name = trace.get("name", "unnamed")
        trace_names[trace_name] = trace_names.get(trace_name, 0) + 1

        # Get observations for this trace
        observations = list_observations(trace_id=trace["id"])
        for obs in observations:
            if obs.get("type") == "GENERATION":
                usage = obs.get("usage") or {}
                total_tokens += usage.get("total_tokens", 0) or 0
                total_cost += obs.get("calculated_total_cost", 0) or 0
                model = obs.get("model", "unknown")
                models[model] = models.get(model, 0) + 1

    return {
        "period_hours": hours,
        "trace_count": len(traces),
        "total_tokens": total_tokens,
        "total_cost": round(total_cost, 4),
        "traces_by_name": trace_names,
        "models_used": models,
    }
