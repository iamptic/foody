import os, math, uuid, secrets, random, string
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends, Query, Header, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from ..db import get_db, engine
from ..models import FoodyRestaurant, FoodyOffer, FoodyReservation

router = APIRouter(prefix="/api/v1", tags=["foody"])

# ---------- helpers ----------
def _now_utc() -> datetime:
    return datetime.now(timezone.utc)

def _gen_restaurant_id() -> str:
    return "RID_" + uuid.uuid4().hex[:8].upper()

def _gen_api_key() -> str:
    return "KEY_" + secrets.token_hex(8)

def _gen_offer_id() -> str:
    return uuid.uuid4().hex

def _gen_code(n=8) -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=n))

async def _auth_key_to_restaurant(db: AsyncSession, api_key: Optional[str]) -> Optional[str]:
    if not api_key:
        return None
    row = (await db.execute(text("SELECT id FROM foody_restaurants WHERE api_key=:k").bindparams(k=api_key))).fetchone()
    return row[0] if row else None

async def _auth_restaurant(db: AsyncSession, restaurant_id: str, api_key: Optional[str]):
    rid_by_key = await _auth_key_to_restaurant(db, api_key)
    if rid_by_key is None or rid_by_key != restaurant_id:
        raise HTTPException(403, "Forbidden")

# ---------- DB bootstrap (simple create if not exists) ----------
async def ensure_schema():
    async with engine.begin() as conn:
        await conn.run_sync(FoodyRestaurant.metadata.create_all, checkfirst=True)
        await conn.run_sync(FoodyOffer.metadata.create_all, checkfirst=True)
        await conn.run_sync(FoodyReservation.metadata.create_all, checkfirst=True)

# ---------- models in/out ----------
class RegisterRestaurantIn(BaseModel):
    title: str
    lat: Optional[float] = None
    lng: Optional[float] = None

class RegisterRestaurantOut(BaseModel):
    restaurant_id: str
    api_key: str
    title: str

class MerchantOfferOut(BaseModel):
    id: str
    restaurant_id: str
    title: str
    price_cents: int
    original_price_cents: Optional[int] = None
    qty_total: int
    qty_left: int
    expires_at: datetime
    created_at: Optional[datetime] = None

class MerchantOfferIn(BaseModel):
    restaurant_id: str
    title: str
    price_rub: Optional[float] = None
    price_cents: Optional[int] = None
    original_price_rub: Optional[float] = None
    original_price_cents: Optional[int] = None
    qty_total: int = 1
    qty_left: Optional[int] = None
    expires_at: datetime

class MerchantOfferPatch(BaseModel):
    title: Optional[str] = None
    price_rub: Optional[float] = None
    price_cents: Optional[int] = None
    original_price_rub: Optional[float] = None
    original_price_cents: Optional[int] = None
    qty_total: Optional[int] = None
    qty_left: Optional[int] = None
    expires_at: Optional[datetime] = None

class BuyerOfferOut(BaseModel):
    id: str
    restaurant_id: str
    restaurant_title: Optional[str] = None
    title: str
    price_cents: int
    original_price_cents: Optional[int] = None
    price_now_cents: int
    qty_left: int
    expires_at: datetime
    distance_km: Optional[float] = None

class CreateReservationIn(BaseModel):
    offer_id: str
    buyer_tg_id: Optional[str] = None

class ReservationOut(BaseModel):
    id: str
    code: str
    status: str
    offer_id: str
    expires_at: datetime

# ---------- routes ----------
@router.post("/auth/register_restaurant", response_model=RegisterRestaurantOut)
async def register_restaurant(body: RegisterRestaurantIn, db: AsyncSession = Depends(get_db)):
    rid = _gen_restaurant_id()
    key = _gen_api_key()
    await db.execute(text("INSERT INTO foody_restaurants(id, title, api_key, lat, lng) VALUES (:i,:t,:k,:la,:ln)")
                     .bindparams(i=rid, t=body.title.strip(), k=key, la=body.lat, ln=body.lng))
    await db.commit()
    return RegisterRestaurantOut(restaurant_id=rid, api_key=key, title=body.title)

@router.get("/merchant/offers", response_model=List[MerchantOfferOut])
async def merchant_offers(
    restaurant_id: str = Query(...),
    x_foody_key: Optional[str] = Header(None, alias="X-Foody-Key"),
    key: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    api_key = x_foody_key or key
    await _auth_restaurant(db, restaurant_id, api_key)
    res = (await db.execute(select(FoodyOffer).where(FoodyOffer.restaurant_id==restaurant_id).order_by(FoodyOffer.created_at.desc()))).scalars().all()
    out = []
    for o in res:
        out.append(MerchantOfferOut(
            id=o.id, restaurant_id=o.restaurant_id, title=o.title, price_cents=o.price_cents,
            original_price_cents=o.original_price_cents, qty_total=o.qty_total, qty_left=o.qty_left,
            expires_at=o.expires_at, created_at=o.created_at
        ))
    return out

@router.post("/merchant/offers", response_model=MerchantOfferOut)
async def merchant_create_offer(
    body: MerchantOfferIn,
    x_foody_key: Optional[str] = Header(None, alias="X-Foody-Key"),
    key: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    api_key = x_foody_key or key
    await _auth_restaurant(db, body.restaurant_id, api_key)
    if not body.title.strip():
        raise HTTPException(422, "title required")
    if body.price_cents is None and body.price_rub is None:
        raise HTTPException(422, "price required (rub or cents)")
    price_cents = body.price_cents if body.price_cents is not None else int(round(body.price_rub * 100))
    if price_cents < 0: raise HTTPException(422, "price >= 0")
    orig_cents = body.original_price_cents if body.original_price_cents is not None else (int(round(body.original_price_rub * 100)) if body.original_price_rub is not None else None)
    qty_total = max(1, int(body.qty_total or 1))
    qty_left = int(body.qty_left if body.qty_left is not None else qty_total)
    if qty_left > qty_total: qty_left = qty_total
    if body.expires_at.tzinfo is None:
        body.expires_at = body.expires_at.replace(tzinfo=timezone.utc)
    oid = _gen_offer_id()
    await db.execute(text("INSERT INTO foody_offers(id, restaurant_id, title, price_cents, original_price_cents, qty_total, qty_left, expires_at) VALUES (:i,:r,:t,:p,:op,:qt,:ql,:e)")
                     .bindparams(i=oid, r=body.restaurant_id, t=body.title.strip(), p=price_cents, op=orig_cents, qt=qty_total, ql=qty_left, e=body.expires_at))
    await db.commit()
    o = (await db.execute(select(FoodyOffer).where(FoodyOffer.id==oid))).scalar_one()
    return MerchantOfferOut(id=o.id, restaurant_id=o.restaurant_id, title=o.title, price_cents=o.price_cents, original_price_cents=o.original_price_cents, qty_total=o.qty_total, qty_left=o.qty_left, expires_at=o.expires_at, created_at=o.created_at)

@router.patch("/merchant/offers/{offer_id}", response_model=MerchantOfferOut)
async def merchant_edit_offer(
    offer_id: str,
    body: MerchantOfferPatch,
    x_foody_key: Optional[str] = Header(None, alias="X-Foody-Key"),
    key: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    rid_by_key = await _auth_key_to_restaurant(db, x_foody_key or key)
    row = (await db.execute(text("SELECT restaurant_id FROM foody_offers WHERE id=:id").bindparams(id=offer_id))).fetchone()
    if not row: raise HTTPException(404, "Offer not found")
    if rid_by_key is None or rid_by_key != row[0]: raise HTTPException(403, "Forbidden")

    sets=[]; params={"id": offer_id}
    if body.title is not None:
        t=body.title.strip()
        if not t: raise HTTPException(422, "title empty")
        sets.append("title=:t"); params["t"]=t
    if body.price_cents is not None:
        if body.price_cents<0: raise HTTPException(422,"price_cents>=0")
        sets.append("price_cents=:pc"); params["pc"]=body.price_cents
    elif body.price_rub is not None:
        pc=int(round(body.price_rub*100)); 
        if pc<0: raise HTTPException(422,"price_rub>=0")
        sets.append("price_cents=:pc"); params["pc"]=pc
    if body.original_price_cents is not None:
        if body.original_price_cents<0: raise HTTPException(422,"original_price_cents>=0")
        sets.append("original_price_cents=:opc"); params["opc"]=body.original_price_cents
    elif body.original_price_rub is not None:
        opc=int(round(body.original_price_rub*100)); sets.append("original_price_cents=:opc"); params["opc"]=opc
    if body.qty_total is not None:
        if body.qty_total<=0: raise HTTPException(422,"qty_total>0")
        sets.append("qty_total=:qt"); params["qt"]=body.qty_total
    if body.qty_left is not None:
        if body.qty_left<0: raise HTTPException(422,"qty_left>=0")
        sets.append("qty_left=:ql"); params["ql"]=body.qty_left
    if body.expires_at is not None:
        exp=body.expires_at
        if exp.tzinfo is None: exp=exp.replace(tzinfo=timezone.utc)
        sets.append("expires_at=:e"); params["e"]=exp

    if not sets:
        o=(await db.execute(select(FoodyOffer).where(FoodyOffer.id==offer_id))).scalar_one()
        return MerchantOfferOut(id=o.id, restaurant_id=o.restaurant_id, title=o.title, price_cents=o.price_cents, original_price_cents=o.original_price_cents, qty_total=o.qty_total, qty_left=o.qty_left, expires_at=o.expires_at, created_at=o.created_at)

    q="UPDATE foody_offers SET "+", ".join(sets)+" WHERE id=:id"
    await db.execute(text(q).bindparams(**params)); await db.commit()
    o=(await db.execute(select(FoodyOffer).where(FoodyOffer.id==offer_id))).scalar_one()
    return MerchantOfferOut(id=o.id, restaurant_id=o.restaurant_id, title=o.title, price_cents=o.price_cents, original_price_cents=o.original_price_cents, qty_total=o.qty_total, qty_left=o.qty_left, expires_at=o.expires_at, created_at=o.created_at)


@router.delete("/merchant/offers/{offer_id}")
async def merchant_delete_offer(
    offer_id: str,
    x_foody_key: Optional[str] = Header(None, alias="X-Foody-Key"),
    key: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    rid_by_key = await _auth_key_to_restaurant(db, x_foody_key or key)
    row = (await db.execute(text("SELECT restaurant_id FROM foody_offers WHERE id=:id").bindparams(id=offer_id))).fetchone()
    if not row: raise HTTPException(404, "Offer not found")
    if rid_by_key is None or rid_by_key != row[0]: raise HTTPException(403, "Forbidden")
    try:
        # If there are active reservations, archive instead of delete
        cnt = (await db.execute(text("SELECT COUNT(*) FROM foody_reservations WHERE offer_id=:id AND status='reserved'").bindparams(id=offer_id))).scalar_one()
        if cnt and cnt > 0:
            await db.execute(text("UPDATE foody_offers SET archived_at=NOW(), qty_left=0 WHERE id=:id").bindparams(id=offer_id))
        else:
            await db.execute(text("DELETE FROM foody_reservations WHERE offer_id=:id").bindparams(id=offer_id))
            await db.execute(text("DELETE FROM foody_offers WHERE id=:id").bindparams(id=offer_id))
        await db.commit()
        return {"ok": True, "deleted_id": offer_id, "archived": bool(cnt)}
    except Exception as e:
        await db.rollback()
        raise HTTPException(500, f"delete failed: {e}")

@router.get("/merchant/report.csv")
async def merchant_report_csv(
    restaurant_id: str = Query(...),
    x_foody_key: Optional[str] = Header(None, alias="X-Foody-Key"),
    key: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    api_key = x_foody_key or key
    await _auth_restaurant(db, restaurant_id, api_key)
    rows = (await db.execute(text(
        "SELECT r.id as reservation_id, r.code, r.status, r.buyer_tg_id, r.created_at, r.redeemed_at, o.title, o.price_cents "
        "FROM foody_reservations r JOIN foody_offers o ON r.offer_id=o.id WHERE r.restaurant_id=:rid ORDER BY r.created_at DESC"
    ).bindparams(rid=restaurant_id))).all()
    import csv, io
    buf=io.StringIO()
    w=csv.writer(buf, lineterminator='\n')
    w.writerow(["reservation_id","code","status","buyer_tg_id","created_at","redeemed_at","offer_title","price_rub"])
    for row in rows:
        price_rub = (row[7] or 0)/100.0
        w.writerow([row[0],row[1],row[2],row[3],row[4],row[5],row[6], f"{price_rub:.2f}"])
    csv_data=buf.getvalue()
    return Response(content=csv_data, media_type='text/csv', headers={'Content-Disposition': f'attachment; filename="foody_report_{restaurant_id}.csv"'})

@router.get("/offers", response_model=List[BuyerOfferOut])
async def public_offers(
    restaurant_id: Optional[str] = Query(None),
    lat: Optional[float] = Query(None),
    lng: Optional[float] = Query(None),
    radius_km: Optional[float] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    # basic filter: not expired and qty_left>0
    q = select(FoodyOffer, FoodyRestaurant.title).join(FoodyRestaurant, FoodyRestaurant.id==FoodyOffer.restaurant_id)
    q = q.where(FoodyOffer.expires_at > _now_utc()).where(FoodyOffer.qty_left > 0)
    if restaurant_id:
        q = q.where(FoodyOffer.restaurant_id==restaurant_id)
    res = (await db.execute(q)).all()
    out=[]
    for o, r_title in res:
        item = BuyerOfferOut(
            id=o.id, restaurant_id=o.restaurant_id, restaurant_title=r_title, title=o.title,
            price_cents=o.price_cents, original_price_cents=o.original_price_cents,
            price_now_cents=o.price_cents, qty_left=o.qty_left, expires_at=o.expires_at
        )
        out.append(item)

    # distance filter
    if lat is not None and lng is not None and radius_km:
        # fetch coords of restaurants
        ids=set([x.restaurant_id for x in out])
        places = (await db.execute(text("SELECT id, lat, lng FROM foody_restaurants WHERE id = ANY(:ids)")
                    .bindparams(ids=list(ids)))).all()
        coords={p[0]:(p[1],p[2]) for p in places}
        filtered=[]
        for item in out:
            la,ln = coords.get(item.restaurant_id, (None,None))
            if la is None or ln is None: 
                # no coords -> skip from geo-filter; but we still want to show something if geo collapses
                continue
            # haversine
            R=6371.0
            import math
            dlat=math.radians(la-lat); dlng=math.radians(ln-lng)
            a=(math.sin(dlat/2)**2 + math.cos(math.radians(lat))*math.cos(math.radians(la))*math.sin(dlng/2)**2)
            c=2*math.atan2(math.sqrt(a),math.sqrt(1-a))
            dist=R*c
            if dist<=radius_km:
                item.distance_km=round(dist,2); filtered.append(item)
        out = filtered

    return out

@router.post("/reservations", response_model=ReservationOut)
async def create_reservation(body: CreateReservationIn, db: AsyncSession = Depends(get_db)):
    o=(await db.execute(select(FoodyOffer).where(FoodyOffer.id==body.offer_id))).scalar_one_or_none()
    if not o: raise HTTPException(404, "Offer not found")
    if o.qty_left<=0: raise HTTPException(409, "Sold out")
    rid=o.restaurant_id
    res_id=str(uuid.uuid4())
    code=_gen_code()
    ttl_min=int(os.getenv("RESERVATION_TTL_MIN","30"))
    exp=min(o.expires_at, _now_utc()+timedelta(minutes=ttl_min))
    await db.execute(text("UPDATE foody_offers SET qty_left=qty_left-1 WHERE id=:id").bindparams(id=o.id))
    await db.execute(text("INSERT INTO foody_reservations(id, offer_id, restaurant_id, code, status, buyer_tg_id, expires_at) VALUES (:i,:o,:r,:c,'reserved',:b,:e)")
                     .bindparams(i=res_id, o=o.id, r=rid, c=code, b=body.buyer_tg_id, e=exp))
    await db.commit()
    return ReservationOut(id=res_id, code=code, status="reserved", offer_id=o.id, expires_at=exp)

class RedeemIn(BaseModel):
    restaurant_id: Optional[str] = None
    code: Optional[str] = None
    res_id: Optional[str] = None

class RedeemOut(BaseModel):
    ok: bool
    reservation_id: Optional[str] = None
    code: Optional[str] = None
    status: Optional[str] = None

@router.get("/merchant/check_code", response_model=RedeemOut)
async def merchant_check_code(restaurant_id: Optional[str] = Query(None), code: Optional[str] = Query(None), res_id: Optional[str] = Query(None),
                              x_foody_key: Optional[str] = Header(None, alias="X-Foody-Key"), key: Optional[str] = Query(None),
                              db: AsyncSession = Depends(get_db)):
    api_key = x_foody_key or key
    rid_by_key = await _auth_key_to_restaurant(db, api_key)
    if not rid_by_key: raise HTTPException(401, "Missing auth")
    cond=""
    if res_id: cond="id=:v"
    elif code: cond="code=:v"
    else: raise HTTPException(422, "code or res_id required")
    row=(await db.execute(text(f"SELECT id, code, status FROM foody_reservations WHERE {cond} AND restaurant_id=:r").bindparams(v=res_id or code, r=rid_by_key))).fetchone()
    if not row: raise HTTPException(404, "Not found")
    return RedeemOut(ok=True, reservation_id=row[0], code=row[1], status=row[2])

@router.post("/merchant/redeem", response_model=RedeemOut)
async def merchant_redeem(body: RedeemIn, x_foody_key: Optional[str] = Header(None, alias="X-Foody-Key"), key: Optional[str] = Query(None),
                          db: AsyncSession = Depends(get_db)):
    api_key = x_foody_key or key
    rid_by_key = await _auth_key_to_restaurant(db, api_key)
    if not rid_by_key: raise HTTPException(401, "Missing auth")
    cond=""
    if body.res_id: cond="id=:v"
    elif body.code: cond="code=:v"
    else: raise HTTPException(422, "code or res_id required")
    row=(await db.execute(text(f"SELECT id, code, status FROM foody_reservations WHERE {cond} AND restaurant_id=:r").bindparams(v=body.res_id or body.code, r=rid_by_key))).fetchone()
    if not row: raise HTTPException(404, "Not found")
    if row[2]=="redeemed": return RedeemOut(ok=True, reservation_id=row[0], code=row[1], status=row[2])
    await db.execute(text("UPDATE foody_reservations SET status='redeemed', redeemed_at=NOW() WHERE id=:i").bindparams(i=row[0]))
    await db.commit()
    return RedeemOut(ok=True, reservation_id=row[0], code=row[1], status="redeemed")
