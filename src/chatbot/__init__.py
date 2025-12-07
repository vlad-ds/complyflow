"""
Chatbot module for RAG-based regulatory Q&A.

Provides conversational interface over regulatory documents indexed in Qdrant.
"""

from chatbot.rag import chat

__all__ = ["chat"]
