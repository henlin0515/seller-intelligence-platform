from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ProductImportRow(BaseModel):
    product_name: str = Field(..., min_length=1)
    product_link: str | None = None
    product_image_url: str | None = None
    sku_variations: list[str] | str | None = None
    price: float | None = None


class OurCatalogImportRequest(BaseModel):
    label: str = "manual"
    products: list[ProductImportRow] = Field(..., min_length=1)


class CompetitorCatalogImportRequest(BaseModel):
    label: str = "manual"
    competitor_shop_id: str | None = None
    competitor_shop_name: str | None = None
    products: list[ProductImportRow] = Field(..., min_length=1)
    run_matching: bool = True


class ImportResponse(BaseModel):
    ok: bool
    import_batch_id: int | None = None
    imported: int = 0
    new_listings: int | None = None
    matching: dict[str, Any] | None = None
