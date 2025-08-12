# app/features/offers_reservations_foody.py
import os, datetime as dt, uuid, secrets
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Query, Header, Body
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import String, DateTime, ForeignKey, text, select, Float, Integer

# --- DB setup (async) ---
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL env is required")
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
Base = declarative_base()

# --- Tables ---
class FoodyRestaurant(Base):
    __tablename__ = "foody_restaurants"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lng: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    api_key: Mapped[Optional[str]] = mapped_column(String, nullable=True)

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

router = APIRouter(prefix="/api/v1", tags=["offers","reservations","merchant"])

async def get_db():
    async with SessionLocal() as session:
        yield session

# --- Buyer: dynamic price helper ---
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

# --- Buyer: create reservation ---
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

@router.post("/reservations", response_model=ReservationOut)
async def create_reservation(body: ReservationCreateIn, db: AsyncSession=Depends(get_db)):
    now = dt.datetime.now(dt.timezone.utc)
    offer = (await db.execute(select(FoodyOffer).where(FoodyOffer.id==body.offer_id))).scalar_one_or_none()
    if not offer:
        raise HTTPException(404, "offer not found")
    if offer.expires_at <= now or offer.qty_left <= 0:
        raise HTTPException(400, "offer unavailable")

    res = await db.execute(
        text("UPDATE foody_offers SET qty_left = qty_left - 1 WHERE id = :id AND qty_left > 0 RETURNING qty_left").bindparams(id=offer.id)
    )
    await db.commit()
    if not res.first():
        raise HTTPException(400, "sold out")

    code = secrets.token_urlsafe(6).replace("-", "").replace("_","")[:8].upper()
    r_id = str(uuid.uuid4())
    await db.execute(text("""            INSERT INTO foody_reservations (id, offer_id, restaurant_id, buyer_tg_id, code, status, expires_at)
        VALUES (:id, :offer_id, :restaurant_id, :buyer_tg_id, :code, 'reserved', :expires_at)
    """        ).bindparams(id=r_id, offer_id=offer.id, restaurant_id=offer.restaurant_id, buyer_tg_id=body.buyer_tg_id, code=code, expires_at=offer.expires_at))
    await db.commit()
    return ReservationOut(
        id=r_id, offer_id=offer.id, restaurant_id=offer.restaurant_id, code=code,
        status="reserved", expires_at=offer.expires_at, qr_payload=f"FOODY|{r_id}|{code}"
    )

# --- Buyer: my reservations (для страницы /buyer/my.html)
class MyReservation(BaseModel):
    id: str
    offer_id: str
    status: str
    expires_at: dt.datetime

@router.get("/my_reservations", response_model=List[MyReservation])
async def my_reservations(buyer_tg_id: str = Query(...), db: AsyncSession=Depends(get_db)):
    q = select(FoodyReservation).where(FoodyReservation.buyer_tg_id == buyer_tg_id).order_by(FoodyReservation.created_at.desc())
    res = (await db.execute(q)).scalars().all()
    return [MyReservation(id=r.id, offer_id=r.offer_id, status=r.status, expires_at=r.expires_at) for r in res]

# --- Merchant API (CRUD) ---
class MerchantOfferIn(BaseModel):
    restaurant_id: str
    title: str
    price_cents: int
    qty_total: int
    qty_left: Optional[int] = None
    expires_at: dt.datetime

class MerchantOfferPatch(BaseModel):
    title: Optional[str] = None
    price_cents: Optional[int] = None
    qty_total: Optional[int] = None
    qty_left: Optional[int] = None
    expires_at: Optional[dt.datetime] = None

class MerchantOfferOut(BaseModel):
    id: str
    restaurant_id: str
    title: str
    price_cents: int
    qty_total: int
    qty_left: int
    expires_at: dt.datetime
    created_at: dt.datetime

async def _auth_restaurant(db: AsyncSession, restaurant_id: str, api_key: Optional[str]):
    if not api_key:
        raise HTTPException(401, "Missing X-Foody-Key")
    r = (await db.execute(select(FoodyRestaurant).where(FoodyRestaurant.id==restaurant_id))).scalar_one_or_none()
    if not r or not r.api_key or r.api_key != api_key:
        raise HTTPException(403, "Invalid API key")
    return r

@router.get("/merchant/offers", response_model=List[MerchantOfferOut])
async def merchant_offers(restaurant_id: str = Query(...), x_foody_key: Optional[str] = Header(None, alias="X-Foody-Key"), db: AsyncSession=Depends(get_db)):
    await _auth_restaurant(db, restaurant_id, x_foody_key)
    q = select(FoodyOffer).where(FoodyOffer.restaurant_id==restaurant_id).order_by(FoodyOffer.created_at.desc())
    res = (await db.execute(q)).scalars().all()
    return [MerchantOfferOut(
        id=o.id, restaurant_id=o.restaurant_id, title=o.title, price_cents=o.price_cents,
        qty_total=o.qty_total, qty_left=o.qty_left, expires_at=o.expires_at, created_at=o.created_at
    ) for o in res]

@router.post("/merchant/offers", response_model=MerchantOfferOut)
async def merchant_create_offer(body: MerchantOfferIn, x_foody_key: Optional[str] = Header(None, alias="X-Foody-Key"), db: AsyncSession=Depends(get_db)):
    await _auth_restaurant(db, body.restaurant_id, x_foody_key)
    oid = str(uuid.uuid4())
    qty_left = body.qty_left if body.qty_left is not None else body.qty_total
    await db.execute(text("""            INSERT INTO foody_offers (id, restaurant_id, title, price_cents, qty_total, qty_left, expires_at)
        VALUES (:id,:rid,:title,:price,:qty_total,:qty_left,:expires_at)
    """        ).bindparams(id=oid, rid=body.restaurant_id, title=body.title, price=body.price_cents, qty_total=body.qty_total, qty_left=qty_left, expires_at=body.expires_at))
    await db.commit()
    o = (await db.execute(select(FoodyOffer).where(FoodyOffer.id==oid))).scalar_one()
    return MerchantOfferOut(
        id=o.id, restaurant_id=o.restaurant_id, title=o.title, price_cents=o.price_cents,
        qty_total=o.qty_total, qty_left=o.qty_left, expires_at=o.expires_at, created_at=o.created_at
    )

@router.patch("/merchant/offers/{offer_id}", response_model=MerchantOfferOut)
async def merchant_update_offer(offer_id: str, body: MerchantOfferPatch, x_foody_key: Optional[str] = Header(None, alias="X-Foody-Key"), db: AsyncSession=Depends(get_db)):
    o = (await db.execute(select(FoodyOffer).where(FoodyOffer.id==offer_id))).scalar_one_or_none()
    if not o:
        raise HTTPException(404, "offer not found")
    await _auth_restaurant(db, o.restaurant_id, x_foody_key)
    sets = []
    params = {"id": offer_id}
    for field in ["title","price_cents","qty_total","qty_left","expires_at"]:
        val = getattr(body, field)
        if val is not None:
            sets.append(f"{field} = :{field}")
            params[field] = val
    if sets:
        sql = "UPDATE foody_offers SET " + ", ".join(sets) + " WHERE id = :id"
        await db.execute(text(sql).bindparams(**params))
        await db.commit()
    o = (await db.execute(select(FoodyOffer).where(FoodyOffer.id==offer_id))).scalar_one()
    return MerchantOfferOut(
        id=o.id, restaurant_id=o.restaurant_id, title=o.title, price_cents=o.price_cents,
        qty_total=o.qty_total, qty_left=o.qty_left, expires_at=o.expires_at, created_at=o.created_at
    )

@router.delete("/merchant/offers/{offer_id}")
async def merchant_delete_offer(offer_id: str, x_foody_key: Optional[str] = Header(None, alias="X-Foody-Key"), db: AsyncSession=Depends(get_db)):
    o = (await db.execute(select(FoodyOffer).where(FoodyOffer.id==offer_id))).scalar_one_or_none()
    if not o:
        raise HTTPException(404, "offer not found")
    await _auth_restaurant(db, o.restaurant_id, x_foody_key)
    await db.execute(text("DELETE FROM foody_offers WHERE id = :id").bindparams(id=offer_id))
    await db.commit()
    return {"ok": True}
