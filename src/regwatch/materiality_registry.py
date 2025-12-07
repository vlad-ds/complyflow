"""
Registry for storing materiality analysis results.

Persists materiality analysis to S3 (Railway) or local file,
allowing the weekly digest service to read without re-analyzing.
"""

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime

from regwatch.storage import get_storage

logger = logging.getLogger(__name__)

# Registry is stored at the root of the regwatch cache
REGISTRY_SUBFOLDER = None


@dataclass
class MaterialityRecord:
    """Record of a materiality analysis for a document."""

    celex: str
    topic: str
    title: str
    analyzed_at: str  # ISO format datetime
    is_material: bool
    relevance: str  # high, medium, low, none
    summary: str
    impact: str | None
    action_required: str | None
    eurlex_url: str
    slack_notified: bool  # Whether Slack notification was sent

    @classmethod
    def create(
        cls,
        celex: str,
        topic: str,
        title: str,
        is_material: bool,
        relevance: str,
        summary: str,
        impact: str | None,
        action_required: str | None,
        eurlex_url: str,
        slack_notified: bool = False,
    ) -> "MaterialityRecord":
        """Create a new materiality record with current timestamp."""
        return cls(
            celex=celex,
            topic=topic,
            title=title,
            analyzed_at=datetime.utcnow().isoformat(),
            is_material=is_material,
            relevance=relevance,
            summary=summary,
            impact=impact,
            action_required=action_required,
            eurlex_url=eurlex_url,
            slack_notified=slack_notified,
        )


class MaterialityRegistry:
    """
    Track materiality analysis results in S3/local JSON file.

    This registry stores the results of materiality analysis for each document,
    allowing the weekly digest service to generate summaries without re-analyzing.
    """

    def __init__(self, filename: str = "materiality_results.json"):
        self.filename = filename
        self._records: dict[str, MaterialityRecord] = {}
        self._dirty = False

    def load(self) -> None:
        """Load registry from storage."""
        storage = get_storage()
        key = self.filename.replace(".json", "")
        content = storage.read(key, subfolder=REGISTRY_SUBFOLDER)

        if content:
            try:
                data = json.loads(content)
                self._records = {
                    celex: MaterialityRecord(**record) for celex, record in data.items()
                }
                logger.info(f"Loaded materiality registry with {len(self._records)} records")
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Failed to parse materiality registry, starting fresh: {e}")
                self._records = {}
        else:
            logger.info("No existing materiality registry found, starting fresh")
            self._records = {}

        self._dirty = False

    def save(self) -> None:
        """Save registry to storage."""
        if not self._dirty:
            logger.debug("Materiality registry not modified, skipping save")
            return

        storage = get_storage()
        key = self.filename.replace(".json", "")
        content = json.dumps(
            {celex: asdict(record) for celex, record in self._records.items()},
            indent=2,
        )
        storage.write(key, content, subfolder=REGISTRY_SUBFOLDER)
        logger.info(f"Saved materiality registry with {len(self._records)} records")
        self._dirty = False

    def has_analysis(self, celex: str) -> bool:
        """Check if a document has been analyzed."""
        return celex in self._records

    def add_result(
        self,
        celex: str,
        topic: str,
        title: str,
        is_material: bool,
        relevance: str,
        summary: str,
        impact: str | None,
        action_required: str | None,
        eurlex_url: str,
        slack_notified: bool = False,
    ) -> MaterialityRecord:
        """Add a materiality analysis result."""
        record = MaterialityRecord.create(
            celex=celex,
            topic=topic,
            title=title,
            is_material=is_material,
            relevance=relevance,
            summary=summary,
            impact=impact,
            action_required=action_required,
            eurlex_url=eurlex_url,
            slack_notified=slack_notified,
        )
        self._records[celex] = record
        self._dirty = True
        logger.debug(f"Added materiality result for {celex}: material={is_material}, relevance={relevance}")
        return record

    def mark_slack_notified(self, celex: str) -> None:
        """Mark a document as having had Slack notification sent."""
        if celex in self._records:
            # Create a new record with slack_notified=True
            old = self._records[celex]
            self._records[celex] = MaterialityRecord(
                celex=old.celex,
                topic=old.topic,
                title=old.title,
                analyzed_at=old.analyzed_at,
                is_material=old.is_material,
                relevance=old.relevance,
                summary=old.summary,
                impact=old.impact,
                action_required=old.action_required,
                eurlex_url=old.eurlex_url,
                slack_notified=True,
            )
            self._dirty = True

    def get_record(self, celex: str) -> MaterialityRecord | None:
        """Get a specific materiality record."""
        return self._records.get(celex)

    def get_all_records(self) -> list[MaterialityRecord]:
        """Return all materiality records."""
        return list(self._records.values())

    def get_records_for_period(
        self,
        start_date: str,
        end_date: str,
    ) -> list[MaterialityRecord]:
        """
        Get all records analyzed within a date range.

        Args:
            start_date: ISO format date string (YYYY-MM-DD)
            end_date: ISO format date string (YYYY-MM-DD)

        Returns:
            List of MaterialityRecord objects within the date range
        """
        records = []
        for record in self._records.values():
            # Parse analyzed_at timestamp to date
            try:
                analyzed_date = record.analyzed_at[:10]  # Get YYYY-MM-DD part
                if start_date <= analyzed_date <= end_date:
                    records.append(record)
            except (ValueError, IndexError):
                continue

        # Sort by analyzed_at descending (newest first)
        records.sort(key=lambda r: r.analyzed_at, reverse=True)
        return records

    def get_material_records(self) -> list[MaterialityRecord]:
        """Return only material records."""
        return [r for r in self._records.values() if r.is_material]

    def get_record_count(self) -> int:
        """Return total number of records."""
        return len(self._records)

    def get_material_count(self) -> int:
        """Return count of material records."""
        return sum(1 for r in self._records.values() if r.is_material)
