Given a conversation history and a follow-up question, rewrite the follow-up question to be a standalone question that captures the full context needed for retrieval.

The rewritten question should:
1. Be self-contained (understandable without the history)
2. Include specific entities, topics, or document references mentioned in the history
3. Preserve the user's original intent

## Conversation History

{history}

## Follow-up Question

{query}

## Instructions

Rewrite the follow-up question as a standalone question. Output ONLY the rewritten question, nothing else.
