"""Knowledge base manager – scans domain directories, loads FAQs, builds indices."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from app.core.config import get_index_config

logger = logging.getLogger(__name__)

KNOWLEDGE_BASE_DIR = Path(__file__).parent.parent.parent / "knowledge_base"
DOMAINS_DIR = KNOWLEDGE_BASE_DIR / "domains"
GLOBAL_DIR = KNOWLEDGE_BASE_DIR / "global"


class KnowledgeBaseManager:
    """Manages the on-disk knowledge base and coordinates index building.

    Directory layout expected:
      knowledge_base/
        domains/
          <domain>/
            domain_summary.md
            faqs/
              <domain>_faq.json
        global/
          global_faq.json
        index_config.yaml
    """

    def __init__(self, embedding_service=None) -> None:
        self._config = get_index_config()
        self._embedding_service = embedding_service
        self._indexer = None
        self._domains_cache: list[dict] | None = None

    async def _ensure_services(self):
        if self._embedding_service is None:
            from app.rag.embedding import EmbeddingService
            self._embedding_service = await EmbeddingService.get_instance()
        if self._indexer is None:
            from app.rag.indexer import Indexer
            self._indexer = Indexer(embedding_service=self._embedding_service)

    # ── Domain discovery ──────────────────────────────────────────

    def _list_domain_dirs(self) -> list[Path]:
        """Return a list of domain directory Paths under knowledge_base/domains/."""
        if not DOMAINS_DIR.exists():
            logger.warning("Domains directory not found: %s", DOMAINS_DIR)
            return []
        return sorted([
            p for p in DOMAINS_DIR.iterdir()
            if p.is_dir() and (p / "domain_summary.md").exists()
        ])

    def load_all_domains(self) -> list[dict]:
        """Return metadata for all discovered domains.

        Returns:
            List of dicts with keys: id, name, summary, faq_count
        """
        if self._domains_cache is not None:
            return self._domains_cache

        domains: list[dict] = []
        for domain_dir in self._list_domain_dirs():
            domain_name = domain_dir.name
            summary = self.get_domain_summary(domain_name)
            faqs = self.load_domain_faqs(domain_name)
            domains.append({
                "id": domain_name,
                "name": domain_name,
                "summary": summary,
                "faq_count": len(faqs),
            })

        self._domains_cache = domains
        return domains

    def _invalidate_cache(self) -> None:
        self._domains_cache = None

    # ── Domain summary ────────────────────────────────────────────

    def get_domain_summary(self, domain: str) -> str:
        """Read the domain_summary.md for a given domain name.

        Args:
            domain: domain directory name (e.g. 'account').

        Returns:
            The full markdown content of domain_summary.md, or empty string.
        """
        summary_path = DOMAINS_DIR / domain / "domain_summary.md"
        if not summary_path.exists():
            logger.warning("Domain summary not found: %s", summary_path)
            return ""
        return summary_path.read_text(encoding="utf-8")

    # ── FAQ loading ───────────────────────────────────────────────

    def load_domain_faqs(self, domain: str) -> list[dict]:
        """Load all FAQ items for a domain.

        Scans <domain>/faqs/*.json and merges the arrays.

        Args:
            domain: domain directory name.

        Returns:
            List of FAQ dicts.
        """
        faqs_dir = DOMAINS_DIR / domain / "faqs"
        if not faqs_dir.exists():
            logger.warning("FAQs directory not found: %s", faqs_dir)
            return []

        faqs: list[dict] = []
        for json_path in sorted(faqs_dir.glob("*.json")):
            try:
                with open(json_path, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    faqs.extend(data)
                elif isinstance(data, dict):
                    faqs.append(data)
                logger.debug("Loaded %d FAQ(s) from %s", len(data) if isinstance(data, list) else 1, json_path.name)
            except (json.JSONDecodeError, OSError) as e:
                logger.error("Failed to load FAQ file %s: %s", json_path, e)

        return faqs

    def load_global_faqs(self) -> list[dict]:
        """Load the global FAQ entries."""
        global_faq_path = GLOBAL_DIR / "global_faq.json"
        if not global_faq_path.exists():
            logger.warning("Global FAQ file not found: %s", global_faq_path)
            return []
        try:
            with open(global_faq_path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
            return [data]
        except (json.JSONDecodeError, OSError) as e:
            logger.error("Failed to load global FAQs: %s", e)
            return []

    # ── Index building ────────────────────────────────────────────

    async def build_all_indices(self) -> dict[str, int]:
        """Build ChromaDB indices for all configured domains.

        Returns:
            Dict mapping domain name -> document count indexed.
        """
        await self._ensure_services()

        all_items: list[dict] = []

        # Load per-domain FAQs
        configured_domains = self._config.domains or []
        if not configured_domains:
            # Fallback: discover from filesystem
            configured_domains = [d["id"] for d in self.load_all_domains()]

        for domain in configured_domains:
            faqs = self.load_domain_faqs(domain)
            if faqs:
                all_items.extend(faqs)
                logger.info("Loaded %d FAQ(s) for domain '%s'", len(faqs), domain)
            else:
                logger.warning("No FAQs found for domain '%s'", domain)

        # Load global FAQs
        global_faqs = self.load_global_faqs()
        if global_faqs:
            all_items.extend(global_faqs)
            logger.info("Loaded %d global FAQ(s)", len(global_faqs))

        # Build index
        if all_items:
            await self._indexer.build_index(all_items)
            logger.info("All indices built: %d total documents.", len(all_items))
        else:
            logger.warning("No FAQ items found to index.")

        # Count per domain
        domain_counts: dict[str, int] = {}
        for item in all_items:
            domain = item.get("domain", "global")
            domain_counts[domain] = domain_counts.get(domain, 0) + 1

        return domain_counts

    async def reload_domain(self, domain: str) -> int:
        """Reload a single domain's FAQs into the index.

        Deletes existing docs for the domain first, then re-adds.
        """
        await self._ensure_services()

        faqs = self.load_domain_faqs(domain)
        if not faqs:
            logger.warning("No FAQs found to reload for domain '%s'", domain)
            return 0

        # Delete existing domain docs (crude approach: fetch by domain filter and delete)
        collection = self._indexer._get_collection()
        try:
            existing = collection.get(where={"domain": domain})
            if existing.get("ids"):
                self._indexer.delete_documents(existing["ids"])
                logger.info("Deleted %d existing doc(s) for domain '%s'", len(existing["ids"]), domain)
        except Exception as e:
            logger.warning("Could not delete existing domain docs: %s", e)

        await self._indexer.add_documents(faqs)
        self._invalidate_cache()
        logger.info("Reloaded %d FAQ(s) for domain '%s'", len(faqs), domain)
        return len(faqs)

    def get_domain_faq_count(self, domain: str) -> int:
        """Return the number of FAQ items for a domain."""
        return len(self.load_domain_faqs(domain))

# Singleton instance
knowledge_base_manager = KnowledgeBaseManager()
