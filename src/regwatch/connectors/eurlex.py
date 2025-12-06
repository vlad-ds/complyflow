"""
EUR-Lex RSS connector for fetching EU regulatory documents.

Parses RSS feeds from EUR-Lex custom alerts to extract regulatory updates.
Uses Jina.ai Reader API to fetch full document text (bypasses EUR-Lex WAF).

Alternative API (not currently used):
- Cellar API: http://publications.europa.eu/resource/celex/{CELEX}.ENG
- Fast, no auth required, but only works for published documents
- New proposals (52025xxx) return 404 until officially published
- To use: GET with header "Accept: application/xhtml+xml"
"""

import asyncio
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

import httpx

from regwatch.config import (
    DOC_TYPE_KEYWORDS,
    EURLEX_DOC_URL,
    EURLEX_SKIP_PATTERNS,
    HTTPX_TIMEOUT_SECONDS,
    JINA_API_KEY,
    JINA_READER_URL,
    JINA_TIMEOUT_SECONDS,
    MAX_RETRIES,
    MIN_VALID_CONTENT_LENGTH,
    RETRY_DELAY_SECONDS,
    RETRYABLE_HTTP_CODES,
    RSSFeed,
)
from regwatch.connectors.base import BaseConnector, Document
from regwatch.storage import get_storage

logger = logging.getLogger(__name__)


class EURLexConnector(BaseConnector):
    """Connector for EUR-Lex RSS feeds with full-text extraction via Jina.ai."""

    source_id = "eurlex"
    source_name = "EUR-Lex"

    def __init__(self, feed: RSSFeed):
        """
        Initialize connector with a specific RSS feed.

        Args:
            feed: RSSFeed configuration object
        """
        self.feed = feed
        self.client = httpx.AsyncClient(timeout=30.0)

    async def close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    async def fetch_recent(self, days: int = 7, limit: int = 10) -> list[Document]:
        """
        Fetch recent documents from the RSS feed.

        Args:
            days: Number of days to look back (filters by pubDate)
            limit: Maximum number of documents to return

        Returns:
            List of Document objects
        """
        response = await self.client.get(self.feed.url)
        response.raise_for_status()

        documents = self._parse_rss(response.text)

        if days > 0:
            cutoff = datetime.now().date() - timedelta(days=days)
            documents = [
                doc
                for doc in documents
                if doc.publication_date and doc.publication_date >= cutoff
            ]

        return documents[:limit]

    async def fetch_all(
        self, limit: int = 10, fetch_full_text: bool = False
    ) -> list[Document]:
        """
        Fetch all documents from the RSS feed (no date filter).

        Args:
            limit: Maximum number of documents to return
            fetch_full_text: If True, fetch full document text via Jina.ai

        Returns:
            List of Document objects
        """
        logger.info(f"Fetching RSS feed: {self.feed.name} ({self.feed.topic})")

        try:
            response = await self.client.get(self.feed.url)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"Failed to fetch RSS feed {self.feed.name}: HTTP {e.response.status_code}"
            )
            return []
        except Exception as e:
            logger.error(
                f"Failed to fetch RSS feed {self.feed.name}: {type(e).__name__}: {e}"
            )
            return []

        documents = self._parse_rss(response.text)[:limit]
        logger.info(f"Parsed {len(documents)} documents from RSS feed")

        if fetch_full_text:
            await self._fetch_full_text_for_documents(documents)

        return documents

    async def fetch_document(self, url: str) -> Document | None:
        """
        Fetch a single document by URL.

        Extracts the CELEX number from the URL and fetches the full
        document text via Jina.ai.
        """
        celex = self._extract_celex(url)
        if not celex:
            return None

        full_text = await self.fetch_full_text(celex)
        if not full_text:
            return None

        return Document(
            url=url,
            title=celex,
            source=self.source_id,
            content=full_text,
            doc_id=celex,
            topics=[self.feed.topic],
        )

    async def fetch_full_text(self, celex: str) -> str | None:
        """
        Fetch full document text via Jina.ai Reader.

        Uses Jina.ai's proxy mode with wait-for-selector to bypass EUR-Lex
        WAF protection and ensure content is fully rendered.

        Args:
            celex: CELEX number (e.g., "32022R2554")

        Returns:
            Plain text content of the document, or None if fetch failed
        """
        clean_celex = self._clean_celex(celex)

        # Check cache first
        cached = self._read_cache(clean_celex)
        if cached:
            return cached

        logger.info(f"Fetching document {clean_celex} via Jina.ai")

        # Construct URLs
        eurlex_url = EURLEX_DOC_URL.format(celex=clean_celex)
        jina_url = f"{JINA_READER_URL}/{eurlex_url}"

        # Fetch with retry
        content = await self._fetch_with_retry(jina_url, clean_celex)
        if not content:
            return None

        # Extract and cache
        extracted = self._extract_jina_content(content)
        logger.info(f"Successfully fetched {clean_celex}: {len(extracted)} chars")
        self._write_cache(clean_celex, extracted)

        return extracted

    async def health_check(self) -> bool:
        """Check if the RSS feed is accessible."""
        try:
            response = await self.client.head(self.feed.url)
            return response.status_code == 200
        except Exception:
            return False

    # -------------------------------------------------------------------------
    # Full-text fetching helpers
    # -------------------------------------------------------------------------

    async def _fetch_full_text_for_documents(
        self, documents: list[Document]
    ) -> None:
        """Fetch full text for a list of documents, updating them in place."""
        logger.info(f"Fetching full text for {len(documents)} documents...")
        success_count = 0

        for doc in documents:
            if doc.doc_id:
                full_text = await self.fetch_full_text(doc.doc_id)
                if full_text:
                    success_count += 1
                    doc.content = full_text

        logger.info(
            f"Full text fetch complete: {success_count}/{len(documents)} succeeded"
        )

    async def _fetch_with_retry(self, url: str, celex: str) -> str | None:
        """
        Fetch URL with retry logic for transient failures.

        Returns raw response text or None if all attempts fail.
        """
        headers = self._build_jina_headers()

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = await self.client.get(
                    url, headers=headers, timeout=HTTPX_TIMEOUT_SECONDS
                )
                response.raise_for_status()
                content = response.text

                # Validate response has actual content
                if len(content) < MIN_VALID_CONTENT_LENGTH:
                    if attempt < MAX_RETRIES:
                        logger.warning(
                            f"Attempt {attempt}/{MAX_RETRIES} for {celex}: "
                            f"Response too short ({len(content)} chars), retrying..."
                        )
                        await asyncio.sleep(RETRY_DELAY_SECONDS)
                        continue
                    logger.error(
                        f"Failed to fetch {celex}: Response too short "
                        f"({len(content)} chars), likely WAF challenge"
                    )
                    return None

                return content

            except httpx.HTTPStatusError as e:
                if not self._should_retry(e.response.status_code, attempt):
                    logger.error(f"Failed to fetch {celex}: HTTP {e.response.status_code}")
                    return None
                logger.warning(
                    f"Attempt {attempt}/{MAX_RETRIES} for {celex}: "
                    f"HTTP {e.response.status_code}, retrying..."
                )
                await asyncio.sleep(RETRY_DELAY_SECONDS)

            except httpx.TimeoutException:
                if attempt >= MAX_RETRIES:
                    logger.error(f"Failed to fetch {celex}: Request timed out")
                    return None
                logger.warning(
                    f"Attempt {attempt}/{MAX_RETRIES} for {celex}: Timeout, retrying..."
                )
                await asyncio.sleep(RETRY_DELAY_SECONDS)

            except Exception as e:
                logger.error(f"Failed to fetch {celex}: {type(e).__name__}: {e}")
                return None

        return None

    def _should_retry(self, status_code: int, attempt: int) -> bool:
        """Determine if we should retry based on HTTP status code."""
        return status_code in RETRYABLE_HTTP_CODES and attempt < MAX_RETRIES

    def _build_jina_headers(self) -> dict[str, str]:
        """Build headers for Jina.ai API request."""
        headers = {
            "X-Proxy-Url": "true",  # Proxy mode for WAF bypass
            "X-Wait-For-Selector": "#document1",  # Wait for main content
            "X-Timeout": str(JINA_TIMEOUT_SECONDS),
            "X-No-Cache": "true",  # Bypass cached failures
        }
        if JINA_API_KEY:
            headers["Authorization"] = f"Bearer {JINA_API_KEY}"
        return headers

    # -------------------------------------------------------------------------
    # Cache helpers (uses S3 on Railway, local filesystem in development)
    # -------------------------------------------------------------------------

    def _read_cache(self, celex: str) -> str | None:
        """Read document from cache if valid."""
        storage = get_storage()
        content = storage.read(celex)
        if content and len(content) >= MIN_VALID_CONTENT_LENGTH:
            logger.info(f"Cache hit for {celex}: {len(content)} chars")
            return content
        return None

    def _write_cache(self, celex: str, content: str) -> None:
        """Write document to cache."""
        storage = get_storage()
        storage.write(celex, content)

    # -------------------------------------------------------------------------
    # Content extraction helpers
    # -------------------------------------------------------------------------

    def _extract_jina_content(self, markdown: str) -> str:
        """
        Extract main content from Jina.ai markdown response.

        Removes Jina metadata headers and EUR-Lex navigation elements.
        """
        lines = markdown.split("\n")
        content_lines = []
        in_content = False

        for line in lines:
            # Skip Jina metadata headers
            if line.startswith("Title:") or line.startswith("URL Source:"):
                continue
            if line.startswith("Markdown Content:"):
                in_content = True
                continue

            if in_content:
                # Skip navigation/UI patterns
                if any(pattern in line for pattern in EURLEX_SKIP_PATTERNS):
                    continue
                content_lines.append(line)

        return "\n".join(content_lines).strip()

    def _clean_celex(self, celex: str) -> str:
        """Clean CELEX number by removing parenthetical suffixes like R(09)."""
        return re.sub(r"\([^)]+\)$", "", celex)

    def _extract_celex(self, url: str) -> str | None:
        """Extract CELEX number from EUR-Lex URL."""
        if "CELEX:" in url:
            start = url.find("CELEX:") + 6
            end = url.find("&", start)
            if end == -1:
                end = len(url)
            return url[start:end]
        return None

    # -------------------------------------------------------------------------
    # RSS parsing
    # -------------------------------------------------------------------------

    def _parse_rss(self, xml_content: str) -> list[Document]:
        """Parse RSS XML content into Document objects."""
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            logger.error(f"Failed to parse RSS XML: {e}")
            return []

        channel = root.find("channel")
        if channel is None:
            return []

        documents = []
        for item in channel.findall("item"):
            doc = self._parse_item(item)
            if doc:
                documents.append(doc)

        return documents

    def _parse_item(self, item: ET.Element) -> Document | None:
        """Parse a single RSS item into a Document."""
        title_el = item.find("title")
        link_el = item.find("link")

        if title_el is None or link_el is None:
            return None

        title = title_el.text or ""
        url = link_el.text or ""

        if not title or not url:
            return None

        # Extract optional fields
        description = ""
        desc_el = item.find("description")
        if desc_el is not None and desc_el.text:
            description = desc_el.text

        # Parse publication date
        pub_date = None
        pub_date_el = item.find("pubDate")
        if pub_date_el is not None and pub_date_el.text:
            try:
                pub_date = parsedate_to_datetime(pub_date_el.text).date()
            except (ValueError, TypeError):
                pass

        return Document(
            url=url,
            title=title.strip(),
            source=self.source_id,
            content=description,
            summary=description[:500] if description else None,
            doc_type=self._infer_doc_type(title, description),
            topics=[self.feed.topic],
            publication_date=pub_date,
            doc_id=self._extract_celex(url),
        )

    def _infer_doc_type(self, title: str, description: str) -> str:
        """Infer document type from title and description."""
        text = (title + " " + description).lower()

        for doc_type, keywords in DOC_TYPE_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                return doc_type

        return "other"
