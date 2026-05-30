from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seller.assortment.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ImportBatch(Base):
    """Manual import batch — future scraper runs will create batches too."""

    __tablename__ = "assortment_import_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    label: Mapped[str] = mapped_column(String(255), default="manual")
    source_type: Mapped[str] = mapped_column(String(32), default="manual")  # manual | scraper (future)
    catalog_type: Mapped[str] = mapped_column(String(32))  # our | competitor
    competitor_shop_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    competitor_shop_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    product_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    our_products: Mapped[list["OurProduct"]] = relationship(back_populates="import_batch")
    competitor_products: Mapped[list["CompetitorProduct"]] = relationship(back_populates="import_batch")


class OurProduct(Base):
    __tablename__ = "assortment_our_products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey("assortment_import_batches.id"), nullable=True)
    product_name: Mapped[str] = mapped_column(String(512))
    product_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    sku_variations: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    import_batch: Mapped[ImportBatch | None] = relationship(back_populates="our_products")
    matches: Mapped[list["ProductMatch"]] = relationship(
        back_populates="our_product",
        foreign_keys="ProductMatch.our_product_id",
    )


class CompetitorProduct(Base):
    __tablename__ = "assortment_competitor_products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey("assortment_import_batches.id"), nullable=True)
    competitor_shop_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    product_name: Mapped[str] = mapped_column(String(512))
    product_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    sku_variations: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    first_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    is_new_listing: Mapped[bool] = mapped_column(Boolean, default=True)
    # Future scraper plug-in: external_id, raw_payload_json, scrape_status, etc.
    external_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    import_batch: Mapped[ImportBatch | None] = relationship(back_populates="competitor_products")
    matches: Mapped[list["ProductMatch"]] = relationship(
        back_populates="competitor_product",
        foreign_keys="ProductMatch.competitor_product_id",
    )


class TrackerFetchStatus(Base):
    """Last catalog fetch attempt per COMPETITOR_TRACKER seller (shop_id)."""

    __tablename__ = "assortment_tracker_fetch_status"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    seller_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    seller_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    shopee_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    tiktok_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    catalog_status: Mapped[str] = mapped_column(String(16), default="na")  # ok | na
    catalog_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_count: Mapped[int] = mapped_column(Integer, default=0)
    shop_link_attempted: Mapped[str | None] = mapped_column(Text, nullable=True)
    link_results_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProductMatch(Base):
    """Best-match row per competitor product (recomputed after import)."""

    __tablename__ = "assortment_product_matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    our_product_id: Mapped[int | None] = mapped_column(ForeignKey("assortment_our_products.id"), nullable=True)
    competitor_product_id: Mapped[int] = mapped_column(
        ForeignKey("assortment_competitor_products.id"),
        nullable=False,
        index=True,
    )
    image_similarity: Mapped[float] = mapped_column(Float, default=0.0)
    title_similarity: Mapped[float] = mapped_column(Float, default=0.0)
    sku_similarity: Mapped[float] = mapped_column(Float, default=0.0)
    similarity_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    match_status: Mapped[str] = mapped_column(String(32), index=True)
    human_reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    human_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    our_product: Mapped[OurProduct | None] = relationship(
        back_populates="matches",
        foreign_keys=[our_product_id],
    )
    competitor_product: Mapped[CompetitorProduct] = relationship(
        back_populates="matches",
        foreign_keys=[competitor_product_id],
    )
