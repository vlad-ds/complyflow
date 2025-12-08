"""
Contracts chatbot module.

Q&A chatbot for the compliance team to ask questions about contracts.
Uses Claude Sonnet 4.5 with:
- Code Execution Tool for structured data analysis (Airtable CSV)
- Custom search_contracts tool for semantic search (Qdrant)
- Search Results feature for proper citations
"""

from contracts_chat.chat import chat, ChatMessage, ChatResult

__all__ = ["chat", "ChatMessage", "ChatResult"]
