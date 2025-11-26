---
name: langfuse
description: Access and analyze Langfuse observability data including traces, observations, token usage, and costs. Use when the user asks about LLM traces, debugging API calls, checking token usage, viewing Langfuse dashboard data, or analyzing LLM costs.
---

# Langfuse Data Access

Use the `src/langfuse_client.py` module to query Langfuse observability data.

## Available Functions

### List Recent Traces
```python
from src.langfuse_client import list_traces
traces = list_traces(limit=20)
```

Filter options: `user_id`, `session_id`, `name`, `tags`, `from_timestamp`, `to_timestamp`

### Get Trace Details
```python
from src.langfuse_client import get_trace
trace = get_trace("trace-id-here")
```

### List Observations (Generations/Spans)
```python
from src.langfuse_client import list_observations
observations = list_observations(trace_id="trace-id", obs_type="GENERATION")
```

Filter options: `trace_id`, `name`, `obs_type` (GENERATION, SPAN, EVENT), `from_start_time`, `to_start_time`

### Get Observation Details
```python
from src.langfuse_client import get_observation
obs = get_observation("observation-id")
# Returns full details including input/output content
```

### Get Trace Summary
```python
from src.langfuse_client import get_trace_summary
summary = get_trace_summary("trace-id")
# Returns: trace metadata, total tokens, total cost, generation breakdown
```

### Get Recent Activity Overview
```python
from src.langfuse_client import get_recent_activity
activity = get_recent_activity(hours=24, limit=50)
# Returns: trace count, total tokens, total cost, models used, traces by name
```

### List Sessions
```python
from src.langfuse_client import list_sessions
sessions = list_sessions(limit=20)
```

## Usage Instructions

1. Always run scripts with `uv run python` to ensure dependencies are available
2. The module auto-loads `.env` for Langfuse credentials
3. All functions return dictionaries for easy inspection
4. All timestamps are in UTC

## Example: Debug a Recent Trace

```python
from src.langfuse_client import list_traces, get_trace_summary

# Get most recent traces
traces = list_traces(limit=5)
for t in traces:
    print(f"{t['id']}: {t['name']} at {t['timestamp']}")

# Get detailed summary of first trace
if traces:
    summary = get_trace_summary(traces[0]['id'])
    print(f"Tokens: {summary['total_tokens']}, Cost: ${summary['total_cost']}")
    for gen in summary['generations']:
        print(f"  - {gen['name']}: {gen['model']} ({gen['input_tokens']} in / {gen['output_tokens']} out, {gen['latency_ms']}ms)")
```

## Example: Check Token Usage

```python
from src.langfuse_client import get_recent_activity

activity = get_recent_activity(hours=24)
print(f"Last 24h: {activity['trace_count']} traces")
print(f"Total tokens: {activity['total_tokens']}")
print(f"Total cost: ${activity['total_cost']}")
print(f"Models: {activity['models_used']}")
```
