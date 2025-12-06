"""
Configuration for regulatory monitoring sources.

EUR-Lex RSS Feeds
-----------------
Created via EUR-Lex account on 2024-12-06 using automated web agent.
Each feed monitors a specific EU regulation/directive with notifications for:
- Modifications to the document
- Subsequent preparatory acts changing the document
- Case-law affecting the document
- Consolidated versions of the document
- Documents related to the document
- Documents mentioning the document
- Documents whose legal basis is the document (delegated/implementing acts)

Management URL: https://eur-lex.europa.eu/protected/my-eurlex/my-rss.html
"""

import os
from dataclasses import dataclass


# =============================================================================
# Cache Configuration
# =============================================================================

MIN_VALID_CONTENT_LENGTH = 1000  # Minimum chars for valid document content


# =============================================================================
# Retry Configuration
# =============================================================================

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 5
RETRYABLE_HTTP_CODES = (503, 524, 429)  # Overloaded, timeout, rate limit


# =============================================================================
# Jina.ai Reader API Configuration
# =============================================================================

JINA_READER_URL = "https://r.jina.ai"
JINA_API_KEY = os.getenv("JINA_API_KEY")
JINA_TIMEOUT_SECONDS = 60
HTTPX_TIMEOUT_SECONDS = 90  # Jina timeout + buffer


# =============================================================================
# EUR-Lex Configuration
# =============================================================================

EURLEX_DOC_URL = "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:{celex}"

# UI/navigation patterns to strip from extracted content
EURLEX_SKIP_PATTERNS = [
    "Skip to main content",
    "Accept all cookies",
    "Accept only essential cookies",
    "You are here",
    "EUROPA",
    "EUR-Lex home",
    "Quick search",
    "Search tips",
    "Need more search options",
    "Document information",
    "Procedure",
    "Permanent link",
    "Download notice",
    "Save to My items",
    "Create an email alert",
    "Create an RSS alert",
    "Languages and formats available",
    "Expand all",
    "Collapse all",
]

# Document type keywords for classification
DOC_TYPE_KEYWORDS = {
    "regulation": ["regulation"],
    "directive": ["directive"],
    "decision": ["decision"],
    "opinion": ["opinion"],
    "recommendation": ["recommendation"],
    "guidelines": ["guideline", "guidelines"],
    "delegated_act": ["delegated"],
    "implementing_act": ["implementing"],
    "case_law": ["judgment", "case"],
}


# =============================================================================
# RSS Feed Configuration
# =============================================================================


@dataclass
class RSSFeed:
    """Configuration for an RSS feed source."""

    name: str  # Human-readable name
    url: str  # RSS feed URL
    topic: str  # Topic category for tagging
    source_doc: str  # Source regulation/directive reference


# EUR-Lex RSS feeds for EU financial regulation
EURLEX_FEEDS: list[RSSFeed] = [
    RSSFeed(
        name="ComplyFlow - DORA",
        url="https://eur-lex.europa.eu/EN/display-feed.rss?myRssId=zqe4qsI%2B%2BF8wdPmn2H1VOiVEJ5x9p0m34pg4xDjTOag%3D",
        topic="DORA",
        source_doc="Regulation (EU) 2022/2554",
    ),
    RSSFeed(
        name="ComplyFlow - MiCA",
        url="https://eur-lex.europa.eu/EN/display-feed.rss?myRssId=zqe4qsI%2B%2BF8wdPmn2H1VOSv%2BP2yZhvxQE3dHsKb%2BV4Q%3D",
        topic="MiCA",
        source_doc="Regulation (EU) 2023/1114",
    ),
    RSSFeed(
        name="ComplyFlow - AIFMD",
        url="https://eur-lex.europa.eu/EN/display-feed.rss?myRssId=zqe4qsI%2B%2BF8wdPmn2H1VOJBoNzzFmZDyvC2SnNMajZ8%3D",
        topic="AIFMD",
        source_doc="Directive 2011/61/EU",
    ),
    RSSFeed(
        name="ComplyFlow - MiFID II",
        url="https://eur-lex.europa.eu/EN/display-feed.rss?myRssId=zqe4qsI%2B%2BF8wdPmn2H1VPzaKDo1RxZef8Km5WZqki9w%3D",
        topic="MiFID",
        source_doc="Directive 2014/65/EU",
    ),
    RSSFeed(
        name="ComplyFlow - AML",
        url="https://eur-lex.europa.eu/EN/display-feed.rss?myRssId=zqe4qsI%2B%2BF8wdPmn2H1VPo0cBt0N2vs9X%2FNsde9AUcc%3D",
        topic="AML",
        source_doc="Regulation (EU) 2024/1624",
    ),
    RSSFeed(
        name="ComplyFlow - AI Act",
        url="https://eur-lex.europa.eu/EN/display-feed.rss?myRssId=zqe4qsI%2B%2BF8wdPmn2H1VPYOmHi3p%2B07arhwTAXFtP%2Bs%3D",
        topic="AI",
        source_doc="Regulation (EU) 2024/1689",
    ),
    RSSFeed(
        name="ComplyFlow - SFDR",
        url="https://eur-lex.europa.eu/EN/display-feed.rss?myRssId=zqe4qsI%2B%2BF8wdPmn2H1VPDgwFn215CJ4AUbGLQSJ5fA%3D",
        topic="ESG",
        source_doc="Regulation (EU) 2019/2088",
    ),
]

# All configured feeds (can add more sources later)
ALL_FEEDS = EURLEX_FEEDS
