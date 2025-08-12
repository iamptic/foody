from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Integer, Float, DateTime, Text, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from .db import Base

class FoodyRestaurant(Base):
    __tablename__ = "foody_restaurants"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    api_key: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped = mapped_column(DateTime(timezone=True), server_default=func.now())
    archived_at: Mapped | None = mapped_column(DateTime(timezone=True), nullable=True)

class FoodyOffer(Base):
    __tablename__ = "foody_offers"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    restaurant_id: Mapped[str] = mapped_column(String, ForeignKey("foody_restaurants.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    original_price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    qty_total: Mapped[int] = mapped_column(Integer, nullable=False)
    qty_left: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped = mapped_column(DateTime(timezone=True), server_default=func.now())
    archived_at: Mapped | None = mapped_column(DateTime(timezone=True), nullable=True)

class FoodyReservation(Base):
    __tablename__ = "foody_reservations"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    offer_id: Mapped[str] = mapped_column(String, ForeignKey("foody_offers.id", ondelete="CASCADE"), index=True)
    restaurant_id: Mapped[str] = mapped_column(String, ForeignKey("foody_restaurants.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String, unique=True, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="reserved")
    buyer_tg_id: Mapped[str | None] = mapped_column(String, nullable=True)
    expires_at: Mapped = mapped_column(DateTime(timezone=True), nullable=False)
    redeemed_at: Mapped = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped = mapped_column(DateTime(timezone=True), server_default=func.now())
    archived_at: Mapped | None = mapped_column(DateTime(timezone=True), nullable=True)
