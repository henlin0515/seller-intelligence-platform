"""
Future competitor scraping plug-in (NOT IMPLEMENTED).

When ready, implement CompetitorScraperProvider with methods:

- fetch_profile_products(profile_url) -> list[dict]
- fetch_shop_products(shop_url) -> list[dict]

Then call import_competitor_products(..., source_type='scraper') and run_matching_for_all_competitors().

Image similarity can be upgraded via similarity.image_similarity(..., provider=YourImageProvider).
"""

from __future__ import annotations

from typing import Any, Protocol


class CompetitorScraperProvider(Protocol):
    def fetch_catalog(self, profile_url: str) -> list[dict[str, Any]]:
        """Return rows with product_name, product_link, product_image_url, sku_variations, price."""
        ...
