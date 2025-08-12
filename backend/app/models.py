
from __future__ import annotations
from typing import Optional, List
from datetime import datetime
from sqlalchemy import String, ForeignKey, DateTime, Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func

class Base(DeclarativeBase):
    pass

class FoodyRestaurant(Base):
    __tablename__ = "foody_restaurants"
    id: Mapped[str] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    lat: Mapped[Optional[float]] = mapped_column(nullable=True)
    lng: Mapped[Optional[float]] = mapped_column(nullable=True)
    staff_pin: Mapped[Optional[str]] = mapped_column(nullable=True)  # 6-значный пин для персонала

    offers: Mapped[List["FoodyOffer"]] = relationship(
        back_populates="restaurant",
        cascade="all, delete-orphan"
    )

class FoodyOffer(Base):
    __tablename__ = "foody_offers"
    id: Mapped[str] = mapped_column(primary_key=True)
    restaurant_id: Mapped[str] = mapped_column(ForeignKey("foody_restaurants.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(256))
    price_cents: Mapped[int] = mapped_column(Integer)
    original_price_cents: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    qty_total: Mapped[int] = mapped_column(Integer)
    qty_left: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    restaurant: Mapped["FoodyRestaurant"] = relationship(back_populates="offers")
    reservations: Mapped[List["FoodyReservation"]] = relationship(
        back_populates="offer",
        cascade="all, delete-orphan"
    )

class FoodyReservation(Base):
    __tablename__ = "foody_reservations"
    id: Mapped[str] = mapped_column(primary_key=True)
    offer_id: Mapped[str] = mapped_column(ForeignKey("foody_offers.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(16), index=True)  # reserved | redeemed | expired
    buyer_tg_id: Mapped[Optional[str]] = mapped_column(nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    redeemed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    offer: Mapped["FoodyOffer"] = relationship(back_populates="reservations")
