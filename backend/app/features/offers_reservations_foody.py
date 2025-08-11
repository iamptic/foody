# app/features/offers_reservations_foody.py
import os, datetime as dt, uuid, secrets
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import String, DateTime, ForeignKey, text, select, Float, Integer

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL env is required")
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
Base = declarative_base()

class FoodyRestaurant(Base):
    __tablename__ = "foody_restaurants"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lng: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

class FoodyOffer(Base):
    __tablename__ = "foody_offers"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    restaurant_id: Mapped[str] = mapped_column(ForeignKey("foody_restaurants.id"), index=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    qty_total: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    qty_left: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc))

class FoodyReservation(Base):
    __tablename__ = "foody_reservations"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    offer_id: Mapped[str] = mapped_column(ForeignKey("foody_offers.id"), index=True)
    restaurant_id: Mapped[str] = mapped_column(ForeignKey("foody_restaurants.id"), index=True)
    buyer_tg_id: Mapped[str] = mapped_column(String, index=True)
    code: Mapped[str] = mapped_column(String, index=True)
    status: Mapped[str] = mapped_column(String, index=True, default="reserved")
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), index=True)
    redeemed_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc))

router = APIRouter(prefix="/api/v1", tags=["offers","reservations"])

async def get_db():
    async with SessionLocal() as session:
        yield session

def compute_dynamic_discount(now: dt.datetime, expires_at: dt.datetime, full_price_cents: int) -> int:
    total = 90 * 60
    remain = (expires_at - now).total_seconds()
    remain = max(0, min(total, remain))
    off = 0.20 + (1 - remain / total) * (0.80 - 0.20)
    off = max(0.20, min(0.80, off))
    discounted = int(round(full_price_cents * (1 - off)))
    return max(0, discounted)

class OfferOut(BaseModel):
    id: str
    restaurant_id: str
    title: str
    price_cents: int
    price_now_cents: int
    qty_left: int
    expires_at: dt.datetime

class ReservationCreateIn(BaseModel):
    offer_id: str
    buyer_tg_id: str = Field(..., description="Telegram user id string")

class ReservationOut(BaseModel):
    id: str
    offer_id: str
    restaurant_id: str
    code: str
    status: str
    expires_at: dt.datetime
    qr_payload: str

class RedeemIn(BaseModel):
    code: str

@router.get("/offers", response_model=List[OfferOut])
async def list_offers(restaurant_id: Optional[str]=None, db: AsyncSession=Depends(get_db)):
    now = dt.datetime.now(dt.timezone.utc)
    q = select(FoodyOffer).where(FoodyOffer.expires_at > now, FoodyOffer.qty_left > 0)
    if restaurant_id:
        q = q.where(FoodyOffer.restaurant_id == restaurant_id)
    q = q.order_by(FoodyOffer.expires_at.asc())
    res = (await db.execute(q)).scalars().all()
    out = []
    for o in res:
        out.append(OfferOut(
            id=o.id, restaurant_id=o.restaurant_id, title=o.title,
            price_cents=o.price_cents, price_now_cents=compute_dynamic_discount(now, o.expires_at, o.price_cents),
            qty_left=o.qty_left, expires_at=o.expires_at
        ))
    return out

@router.post("/reservations", response_model=ReservationOut)
async def create_reservation(body: ReservationCreateIn, db: AsyncSession=Depends(get_db)):
    now = dt.datetime.now(dt.timezone.utc)
    offer = (await db.execute(select(FoodyOffer).where(FoodyOffer.id==body.offer_id))).scalar_one_or_none()
    if not offer:
        raise HTTPException(404, "offer not found")
    if offer.expires_at <= now or offer.qty_left <= 0:
        raise HTTPException(400, "offer unavailable")

    res = await db.execute(
        text("UPDATE foody_offers SET qty_left = qty_left - 1 WHERE id = :id AND qty_left > 0 RETURNING qty_left")
        .bindparams(id=offer.id)
    )
    await db.commit()
    if not res.first():
        raise HTTPException(400, "sold out")

    code = secrets.token_urlsafe(6).replace("-", "").replace("_","")[:8].upper()
    r = FoodyReservation(
        offer_id=offer.id, restaurant_id=offer.restaurant_id,
        buyer_tg_id=body.buyer_tg_id, code=code,
        status="reserved", expires_at=offer.expires_at
    )
    db.add(r)
    await db.commit()
    return ReservationOut(
        id=r.id, offer_id=r.offer_id, restaurant_id=r.restaurant_id, code=r.code,
        status=r.status, expires_at=r.expires_at,
        qr_payload=f"FOODY|{r.id}|{r.code}"
    )

@router.get("/reservations", response_model=List[ReservationOut])
async def list_reservations(restaurant_id: str = Query(...), status: Optional[str]=None, db: AsyncSession=Depends(get_db)):
    q = select(FoodyReservation).where(FoodyReservation.restaurant_id==restaurant_id)
    if status:
        q = q.where(FoodyReservation.status==status)
    q = q.order_by(FoodyReservation.created_at.desc()).limit(200)
    res = (await db.execute(q)).scalars().all()
    return [ReservationOut(
        id=x.id, offer_id=x.offer_id, restaurant_id=x.restaurant_id, code=x.code,
        status=x.status, expires_at=x.expires_at, qr_payload=f"FOODY|{x.id}|{x.code}"
    ) for x in res]

@router.post("/reservations/{reservation_id}/redeem", response_model=ReservationOut)
async def redeem_reservation(reservation_id: str, body: RedeemIn, db: AsyncSession=Depends(get_db)):
    now = dt.datetime.now(dt.timezone.utc)
    r = (await db.execute(select(FoodyReservation).where(FoodyReservation.id==reservation_id))).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "reservation not found")
    if r.code != body.code:
        raise HTTPException(400, "code mismatch")
    if r.status == "redeemed":
        return ReservationOut(
            id=r.id, offer_id=r.offer_id, restaurant_id=r.restaurant_id, code=r.code,
            status=r.status, expires_at=r.expires_at, qr_payload=f"FOODY|{r.id}|{r.code}"
        )
    if r.expires_at <= now:
        r.status = "expired"
        await db.commit()
        raise HTTPException(400, "reservation expired")

    r.status = "redeemed"
    r.redeemed_at = now
    await db.commit()
    return ReservationOut(
        id=r.id, offer_id=r.offer_id, restaurant_id=r.restaurant_id, code=r.code,
        status=r.status, expires_at=r.expires_at, qr_payload=f"FOODY|{r.id}|{r.code}"
    )
