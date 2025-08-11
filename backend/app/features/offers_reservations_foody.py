import os, datetime as dt, uuid, secrets, io
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, Query, Header, FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import String, DateTime, ForeignKey, text, select, Float, Integer, and_

import qrcode
from qrcode.image.pil import PilImage

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
    api_key: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)

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
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    photo_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)

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
merchant = APIRouter(prefix="/api/v1/merchant", tags=["merchant"])

async def get_db():
    async with SessionLocal() as session:
        yield session

# ---------- Helpers ----------
def compute_dynamic_discount(now: dt.datetime, expires_at: dt.datetime, full_price_cents: int) -> int:
    total = 90 * 60
    remain = (expires_at - now).total_seconds()
    remain = max(0, min(total, remain))
    off = 0.20 + (1 - remain / total) * (0.80 - 0.20)
    off = max(0.20, min(0.80, off))
    discounted = int(round(full_price_cents * (1 - off)))
    return max(0, discounted)

async def auth_restaurant_by_key(db: AsyncSession, api_key: str) -> FoodyRestaurant:
    q = select(FoodyRestaurant).where(FoodyRestaurant.api_key == api_key)
    r = (await db.execute(q)).scalar_one_or_none()
    if not r:
        raise HTTPException(401, "invalid api key")
    return r

# ---------- Public Buyer API ----------
class OfferOut(BaseModel):
    id: str
    restaurant_id: str
    title: str
    price_cents: int
    price_now_cents: int
    qty_left: int
    expires_at: dt.datetime
    photo_url: Optional[str] = None
    description: Optional[str] = None

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
            qty_left=o.qty_left, expires_at=o.expires_at, photo_url=o.photo_url, description=o.description
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

@router.get("/my_reservations", response_model=List[ReservationOut])
async def my_reservations(buyer_tg_id: str = Query(...), db: AsyncSession=Depends(get_db)):
    q = select(FoodyReservation).where(FoodyReservation.buyer_tg_id == buyer_tg_id)
    q = q.order_by(FoodyReservation.created_at.desc()).limit(100)
    res = (await db.execute(q)).scalars().all()
    return [ReservationOut(
        id=x.id, offer_id=x.offer_id, restaurant_id=x.restaurant_id, code=x.code,
        status=x.status, expires_at=x.expires_at, qr_payload=f"FOODY|{x.id}|{x.code}"
    ) for x in res]

@router.get("/reservations/{reservation_id}/qr.png")
async def reservation_qr_png(reservation_id: str, db: AsyncSession=Depends(get_db)):
    r = (await db.execute(select(FoodyReservation).where(FoodyReservation.id==reservation_id))).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "reservation not found")
    payload = f"FOODY|{r.id}|{r.code}"
    img = qrcode.make(payload, image_factory=PilImage)
    bio = io.BytesIO()
    img.save(bio, format="PNG")
    bio.seek(0)
    return StreamingResponse(bio, media_type="image/png")

# ---------- Merchant API ----------
class OfferCreateIn(BaseModel):
    restaurant_id: str
    title: str
    price_cents: int
    qty_total: int
    expires_at: dt.datetime
    description: Optional[str] = None
    photo_url: Optional[str] = None

class OfferPatchIn(BaseModel):
    title: Optional[str] = None
    price_cents: Optional[int] = None
    qty_total: Optional[int] = None
    qty_left: Optional[int] = None
    expires_at: Optional[dt.datetime] = None
    description: Optional[str] = None
    photo_url: Optional[str] = None

class OfferFull(BaseModel):
    id: str
    restaurant_id: str
    title: str
    price_cents: int
    qty_total: int
    qty_left: int
    expires_at: dt.datetime
    created_at: dt.datetime
    description: Optional[str] = None
    photo_url: Optional[str] = None

@merchant.get("/offers", response_model=List[OfferFull])
async def merchant_list_offers(restaurant_id: str = Query(...), x_foody_key: str = Header(alias="X-Foody-Key"), db: AsyncSession=Depends(get_db)):
    rest = await auth_restaurant_by_key(db, x_foody_key)
    if rest.id != restaurant_id:
        raise HTTPException(403, "restaurant mismatch")
    q = select(FoodyOffer).where(FoodyOffer.restaurant_id==restaurant_id).order_by(FoodyOffer.created_at.desc())
    res = (await db.execute(q)).scalars().all()
    return [OfferFull(
        id=o.id, restaurant_id=o.restaurant_id, title=o.title, price_cents=o.price_cents,
        qty_total=o.qty_total, qty_left=o.qty_left, expires_at=o.expires_at,
        created_at=o.created_at, description=o.description, photo_url=o.photo_url
    ) for o in res]

@merchant.post("/offers", response_model=OfferFull)
async def merchant_create_offer(body: OfferCreateIn, x_foody_key: str = Header(alias="X-Foody-Key"), db: AsyncSession=Depends(get_db)):
    rest = await auth_restaurant_by_key(db, x_foody_key)
    if rest.id != body.restaurant_id:
        raise HTTPException(403, "restaurant mismatch")
    o = FoodyOffer(
        restaurant_id=body.restaurant_id,
        title=body.title,
        price_cents=body.price_cents,
        qty_total=body.qty_total,
        qty_left=body.qty_total,
        expires_at=body.expires_at,
        description=body.description,
        photo_url=body.photo_url
    )
    db.add(o)
    await db.commit()
    return OfferFull(
        id=o.id, restaurant_id=o.restaurant_id, title=o.title, price_cents=o.price_cents,
        qty_total=o.qty_total, qty_left=o.qty_left, expires_at=o.expires_at,
        created_at=o.created_at, description=o.description, photo_url=o.photo_url
    )

@merchant.patch("/offers/{offer_id}", response_model=OfferFull)
async def merchant_patch_offer(offer_id: str, body: OfferPatchIn, x_foody_key: str = Header(alias="X-Foody-Key"), db: AsyncSession=Depends(get_db)):
    rest = await auth_restaurant_by_key(db, x_foody_key)
    o = (await db.execute(select(FoodyOffer).where(FoodyOffer.id==offer_id))).scalar_one_or_none()
    if not o:
        raise HTTPException(404, "not found")
    if o.restaurant_id != rest.id:
        raise HTTPException(403, "forbidden")
    changed = False
    for f in ["title","price_cents","qty_total","qty_left","expires_at","description","photo_url"]:
        v = getattr(body, f)
        if v is not None:
            setattr(o, f, v); changed = True
    if body.qty_total is not None and (o.qty_left > o.qty_total):
        o.qty_left = o.qty_total
        changed = True
    if changed:
        await db.commit()
    return OfferFull(
        id=o.id, restaurant_id=o.restaurant_id, title=o.title, price_cents=o.price_cents,
        qty_total=o.qty_total, qty_left=o.qty_left, expires_at=o.expires_at,
        created_at=o.created_at, description=o.description, photo_url=o.photo_url
    )

@merchant.delete("/offers/{offer_id}")
async def merchant_delete_offer(offer_id: str, x_foody_key: str = Header(alias="X-Foody-Key"), db: AsyncSession=Depends(get_db)):
    rest = await auth_restaurant_by_key(db, x_foody_key)
    o = (await db.execute(select(FoodyOffer).where(FoodyOffer.id==offer_id))).scalar_one_or_none()
    if not o:
        raise HTTPException(404, "not found")
    if o.restaurant_id != rest.id:
        raise HTTPException(403, "forbidden")
    await db.execute(text("DELETE FROM foody_offers WHERE id = :id").bindparams(id=offer_id))
    await db.commit()
    return {"ok": True}
