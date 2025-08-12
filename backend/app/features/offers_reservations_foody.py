import os, datetime as dt, uuid, secrets, io, math, csv
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Query, Header, Body
from fastapi.responses import Response
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
    api_key: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc))

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

router = APIRouter(prefix="/api/v1", tags=["offers","reservations","merchant","auth"])

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

def haversine_km(lat1, lon1, lat2, lon2):
    import math
    R = 6371.0
    phi1 = math.radians(lat1); phi2=math.radians(lat2)
    dphi = math.radians(lat2-lat1); dl = math.radians(lon2-lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dl/2)**2
    c = 2*math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R*c

class OfferOut(BaseModel):
    id: str
    restaurant_id: str
    restaurant_title: Optional[str] = None
    title: str
    price_cents: int
    price_now_cents: int
    qty_left: int
    expires_at: dt.datetime
    distance_km: Optional[float] = None

@router.get("/offers", response_model=List[OfferOut])
async def list_offers(restaurant_id: Optional[str]=None, lat: Optional[float]=Query(None), lng: Optional[float]=Query(None), radius_km: Optional[float]=Query(None), db: AsyncSession=Depends(get_db)):
    now = dt.datetime.now(dt.timezone.utc)
    q = select(FoodyOffer).where(FoodyOffer.expires_at > now, FoodyOffer.qty_left > 0)
    if restaurant_id: q = q.where(FoodyOffer.restaurant_id == restaurant_id)
    q = q.order_by(FoodyOffer.expires_at.asc())
    offers = (await db.execute(q)).scalars().all()
    rids = sorted({o.restaurant_id for o in offers})
    rmap = {}
    if rids:
        rs = (await db.execute(select(FoodyRestaurant).where(FoodyRestaurant.id.in_(rids)))).scalars().all()
        rmap = {r.id: r for r in rs}
    out = []
    for o in offers:
        r = rmap.get(o.restaurant_id); dist=None
        if lat is not None and lng is not None and r and r.lat is not None and r.lng is not None:
            dist = round(haversine_km(lat, lng, r.lat, r.lng), 2)
            if radius_km is not None and dist > radius_km: continue
        out.append(OfferOut(id=o.id, restaurant_id=o.restaurant_id, restaurant_title=(r.title if r else None), title=o.title, price_cents=o.price_cents, price_now_cents=compute_dynamic_discount(now, o.expires_at, o.price_cents), qty_left=o.qty_left, expires_at=o.expires_at, distance_km=dist))
    if lat is not None and lng is not None:
        out.sort(key=lambda x: (x.distance_km if x.distance_km is not None else 1e9, x.expires_at))
    return out

class RegisterIn(BaseModel):
    title: str; lat: Optional[float]=None; lng: Optional[float]=None
class RegisterOut(BaseModel):
    restaurant_id: str; api_key: str; title: str
def _gen_rest_id():
    return "RID_" + secrets.token_urlsafe(6).replace("-","").replace("_","").upper()[:10]
def _gen_api_key():
    return "fk_" + secrets.token_urlsafe(18).replace("-","").replace("_","")

@router.post("/auth/register_restaurant", response_model=RegisterOut)
async def register_restaurant(body: RegisterIn, db: AsyncSession=Depends(get_db)):
    rid=_gen_rest_id(); key=_gen_api_key()
    await db.execute(text("INSERT INTO foody_restaurants (id, title, lat, lng, api_key) VALUES (:id,:title,:lat,:lng,:key)").bindparams(id=rid, title=body.title.strip(), lat=body.lat, lng=body.lng, key=key))
    await db.commit()
    return RegisterOut(restaurant_id=rid, api_key=key, title=body.title)

class ReservationCreateIn(BaseModel):
    offer_id: str; buyer_tg_id: str = Field(..., description="Telegram user id string")
class ReservationOut(BaseModel):
    id: str; offer_id: str; restaurant_id: str; code: str; status: str; expires_at: dt.datetime; qr_payload: str
@router.post("/reservations", response_model=ReservationOut)
async def create_reservation(body: ReservationCreateIn, db: AsyncSession=Depends(get_db)):
    now = dt.datetime.now(dt.timezone.utc)
    offer = (await db.execute(select(FoodyOffer).where(FoodyOffer.id==body.offer_id))).scalar_one_or_none()
    if not offer: raise HTTPException(404, "offer not found")
    if offer.expires_at <= now or offer.qty_left <= 0: raise HTTPException(400, "offer unavailable")
    res = await db.execute(text("UPDATE foody_offers SET qty_left=qty_left-1 WHERE id=:id AND qty_left>0 RETURNING qty_left").bindparams(id=offer.id)); await db.commit()
    if not res.first(): raise HTTPException(400, "sold out")
    code = secrets.token_urlsafe(6).replace("-","").replace("_","")[:8].upper()
    rid = str(uuid.uuid4())
    await db.execute(text("INSERT INTO foody_reservations (id, offer_id, restaurant_id, buyer_tg_id, code, status, expires_at) VALUES (:id,:offer_id,:restaurant_id,:buyer_tg_id,:code,'reserved',:expires_at)").bindparams(id=rid, offer_id=offer.id, restaurant_id=offer.restaurant_id, buyer_tg_id=body.buyer_tg_id, code=code, expires_at=offer.expires_at))
    await db.commit()
    return ReservationOut(id=rid, offer_id=offer.id, restaurant_id=offer.restaurant_id, code=code, status="reserved", expires_at=offer.expires_at, qr_payload=f"FOODY|{rid}|{code}")

class ReservationDetail(BaseModel):
    id: str; offer_id: str; restaurant_id: str; code: str; status: str; expires_at: dt.datetime
@router.get("/reservations/{res_id}", response_model=ReservationDetail)
async def get_reservation(res_id: str, db: AsyncSession=Depends(get_db)):
    r=(await db.execute(select(FoodyReservation).where(FoodyReservation.id==res_id))).scalar_one_or_none()
    if not r: raise HTTPException(404, "reservation not found")
    return ReservationDetail(id=r.id, offer_id=r.offer_id, restaurant_id=r.restaurant_id, code=r.code, status=r.status, expires_at=r.expires_at)

@router.get("/reservations/{res_id}/qr.png")
async def reservation_qr_png(res_id: str, db: AsyncSession=Depends(get_db)):
    r=(await db.execute(select(FoodyReservation).where(FoodyReservation.id==res_id))).scalar_one_or_none()
    if not r: raise HTTPException(404, "reservation not found")
    payload=f"FOODY|{r.id}|{r.code}"
    try:
        import qrcode, io
        qr=qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=2)
        qr.add_data(payload); qr.make(fit=True)
        img=qr.make_image(fill_color="black", back_color="white")
        bio=io.BytesIO(); img.save(bio, format="PNG")
        return Response(content=bio.getvalue(), media_type="image/png")
    except Exception:
        return Response(content=f"QR: {payload}".encode(), media_type="text/plain")

async def _auth_restaurant(db: AsyncSession, restaurant_id: str, api_key: Optional[str]):
    if not api_key: raise HTTPException(401, "Missing X-Foody-Key")
    r=(await db.execute(select(FoodyRestaurant).where(FoodyRestaurant.id==restaurant_id))).scalar_one_or_none()
    if not r or not r.api_key or r.api_key != api_key: raise HTTPException(403, "Invalid API key")
    return r

class MerchantOfferIn(BaseModel):
    restaurant_id: str; title: str; price_cents: int; qty_total: int; qty_left: Optional[int]=None; expires_at: dt.datetime
class MerchantOfferPatch(BaseModel):
    title: Optional[str]=None; price_cents: Optional[int]=None; qty_total: Optional[int]=None; qty_left: Optional[int]=None; expires_at: Optional[dt.datetime]=None
class MerchantOfferOut(BaseModel):
    id: str; restaurant_id: str; title: str; price_cents: int; qty_total: int; qty_left: int; expires_at: dt.datetime; created_at: dt.datetime

@router.get("/merchant/offers", response_model=List[MerchantOfferOut])
async def merchant_offers(restaurant_id: str = Query(...), x_foody_key: Optional[str] = Header(None, alias="X-Foody-Key"), db: AsyncSession=Depends(get_db)):
    await _auth_restaurant(db, restaurant_id, x_foody_key)
    q=select(FoodyOffer).where(FoodyOffer.restaurant_id==restaurant_id).order_by(FoodyOffer.created_at.desc())
    res=(await db.execute(q)).scalars().all()
    return [MerchantOfferOut(id=o.id, restaurant_id=o.restaurant_id, title=o.title, price_cents=o.price_cents, qty_total=o.qty_total, qty_left=o.qty_left, expires_at=o.expires_at, created_at=o.created_at) for o in res]

@router.post("/merchant/offers", response_model=MerchantOfferOut)
async def merchant_create_offer(body: MerchantOfferIn, x_foody_key: Optional[str] = Header(None, alias="X-Foody-Key"), db: AsyncSession=Depends(get_db)):
    try:
        await _auth_restaurant(db, body.restaurant_id, x_foody_key)
        # Validate
        if not body.title or not body.title.strip():
            raise HTTPException(422, "title is required")
        if body.price_cents is None or body.price_cents < 0:
            raise HTTPException(422, "price_cents must be >= 0")
        if body.qty_total is None or body.qty_total <= 0:
            raise HTTPException(422, "qty_total must be > 0")
        if body.qty_left is not None and (body.qty_left < 0 or body.qty_left > body.qty_total):
            raise HTTPException(422, "qty_left must be between 0 and qty_total")
        exp = body.expires_at
        # Make tz-aware UTC if naive
        import datetime as _dt
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=_dt.timezone.utc)
        now = _dt.datetime.now(_dt.timezone.utc)
        if exp <= now:
            raise HTTPException(422, "expires_at must be in the future (UTC)")
        oid=str(uuid.uuid4())
        qty_left=body.qty_left if body.qty_left is not None else body.qty_total
        await db.execute(text(
            "INSERT INTO foody_offers (id, restaurant_id, title, price_cents, qty_total, qty_left, expires_at) "
            "VALUES (:id,:rid,:title,:price,:qty_total,:qty_left,:expires_at)"
        ).bindparams(id=oid, rid=body.restaurant_id, title=body.title.strip(), price=body.price_cents, qty_total=body.qty_total, qty_left=qty_left, expires_at=exp))
        await db.commit()
        o=(await db.execute(select(FoodyOffer).where(FoodyOffer.id==oid))).scalar_one()
        return MerchantOfferOut(id=o.id, restaurant_id=o.restaurant_id, title=o.title, price_cents=o.price_cents, qty_total=o.qty_total, qty_left=o.qty_left, expires_at=o.expires_at, created_at=o.created_at)
    except HTTPException:
        raise
    except Exception as e:
        # Surface DB/parse errors to client
        raise HTTPException(400, f"create_offer failed: {e}")

@router.patch("/merchant/offers/{offer_id}", response_model=MerchantOfferOut)
async def merchant_update_offer(offer_id: str, body: MerchantOfferPatch, x_foody_key: Optional[str] = Header(None, alias="X-Foody-Key"), db: AsyncSession=Depends(get_db)):
    o=(await db.execute(select(FoodyOffer).where(FoodyOffer.id==offer_id))).scalar_one_or_none()
    if not o: raise HTTPException(404, "offer not found")
    await _auth_restaurant(db, o.restaurant_id, x_foody_key)
    sets=[]; params={"id":offer_id}
    for f in ["title","price_cents","qty_total","qty_left","expires_at"]:
        val=getattr(body, f)
        if val is not None: sets.append(f"{f} = :{f}"); params[f]=val
    if sets:
        await db.execute(text("UPDATE foody_offers SET "+", ".join(sets)+" WHERE id=:id").bindparams(**params)); await db.commit()
    o=(await db.execute(select(FoodyOffer).where(FoodyOffer.id==offer_id))).scalar_one()
    return MerchantOfferOut(id=o.id, restaurant_id=o.restaurant_id, title=o.title, price_cents=o.price_cents, qty_total=o.qty_total, qty_left=o.qty_left, expires_at=o.expires_at, created_at=o.created_at)

@router.delete("/merchant/offers/{offer_id}")
async def merchant_delete_offer(offer_id: str, x_foody_key: Optional[str] = Header(None, alias="X-Foody-Key"), db: AsyncSession=Depends(get_db)):
    o=(await db.execute(select(FoodyOffer).where(FoodyOffer.id==offer_id))).scalar_one_or_none()
    if not o: raise HTTPException(404, "offer not found")
    await _auth_restaurant(db, o.restaurant_id, x_foody_key)
    await db.execute(text("DELETE FROM foody_offers WHERE id=:id").bindparams(id=offer_id)); await db.commit()
    return {"ok": True}

class CheckOut(BaseModel):
    reservation_id: str; code: str; status: str; offer_id: str; expires_at: dt.datetime
@router.get("/merchant/check_code", response_model=CheckOut)
async def check_code(restaurant_id: str = Query(...), code: Optional[str]=Query(None), res_id: Optional[str]=Query(None), x_foody_key: Optional[str]=Header(None, alias="X-Foody-Key"), db: AsyncSession=Depends(get_db)):
    await _auth_restaurant(db, restaurant_id, x_foody_key)
    if not code and not res_id: raise HTTPException(400, "code or res_id required")
    q=select(FoodyReservation).where(FoodyReservation.restaurant_id==restaurant_id)
    if code: q=q.where(FoodyReservation.code==code)
    if res_id: q=q.where(FoodyReservation.id==res_id)
    r=(await db.execute(q)).scalar_one_or_none()
    if not r: raise HTTPException(404, "reservation not found")
    return CheckOut(reservation_id=r.id, code=r.code, status=r.status, offer_id=r.offer_id, expires_at=r.expires_at)

class RedeemIn(BaseModel):
    restaurant_id: str; code: Optional[str]=None; res_id: Optional[str]=None
@router.post("/merchant/redeem")
async def redeem(body: RedeemIn, x_foody_key: Optional[str]=Header(None, alias="X-Foody-Key"), db: AsyncSession=Depends(get_db)):
    await _auth_restaurant(db, body.restaurant_id, x_foody_key)
    if not body.code and not body.res_id: raise HTTPException(400, "code or res_id required")
    q=select(FoodyReservation).where(FoodyReservation.restaurant_id==body.restaurant_id, FoodyReservation.status=="reserved")
    if body.code: q=q.where(FoodyReservation.code==body.code)
    if body.res_id: q=q.where(FoodyReservation.id==body.res_id)
    r=(await db.execute(q)).scalar_one_or_none()
    if not r: raise HTTPException(404, "not found or already redeemed")
    now=dt.datetime.now(dt.timezone.utc)
    if r.expires_at < now: raise HTTPException(400, "expired")
    await db.execute(text("UPDATE foody_reservations SET status='redeemed', redeemed_at=NOW() WHERE id=:id").bindparams(id=r.id)); await db.commit()
    return {"ok": True, "reservation_id": r.id, "code": r.code, "status": "redeemed"}

@router.get("/merchant/report.csv")
async def report_csv(restaurant_id: str=Query(...), date_from: Optional[str]=Query(None), date_to: Optional[str]=Query(None), x_foody_key: Optional[str]=Header(None, alias="X-Foody-Key"), db: AsyncSession=Depends(get_db)):
    await _auth_restaurant(db, restaurant_id, x_foody_key)
    def parse(d):
        if not d: return None
        try:
            return dt.datetime.fromisoformat(d).replace(tzinfo=dt.timezone.utc) if 'T' in d else dt.datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
        except Exception:
            return None
    df=parse(date_from); dt_to=parse(date_to)
    q=select(FoodyReservation, FoodyOffer).where(FoodyReservation.restaurant_id==restaurant_id).join(FoodyOffer, FoodyOffer.id==FoodyReservation.offer_id)
    if df: q=q.where(FoodyReservation.created_at >= df)
    if dt_to: q=q.where(FoodyReservation.created_at < dt_to + dt.timedelta(days=1))
    q=q.order_by(FoodyReservation.created_at.asc())
    rows=(await db.execute(q)).all()
    out=io.StringIO(); import csv as _csv; w=_csv.writer(out)
    w.writerow(["created_at","reservation_id","status","code","offer_id","offer_title","price_cents","expires_at","redeemed_at"])
    for (r,o) in rows:
        w.writerow([r.created_at.isoformat(), r.id, r.status, r.code, r.offer_id, o.title, o.price_cents, r.expires_at.isoformat(), (r.redeemed_at.isoformat() if r.redeemed_at else "")])
    data=out.getvalue().encode("utf-8")
    headers={"Content-Disposition": f"attachment; filename=foody_report_{restaurant_id}.csv"}
    return Response(content=data, media_type="text/csv; charset=utf-8", headers=headers)
