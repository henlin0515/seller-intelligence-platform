"""Assortment Intelligence V1 — mock product data for UI."""

from seller.intelligence.assortment.mock_data import get_mock_assortment_intelligence
from seller.intelligence.assortment.schemas import (
    AssortmentIntelligenceModule,
    AssortmentIntelligenceSeller,
    build_assortment_intelligence_structure,
)

__all__ = [
    "AssortmentIntelligenceModule",
    "AssortmentIntelligenceSeller",
    "build_assortment_intelligence_structure",
    "get_mock_assortment_intelligence",
]
