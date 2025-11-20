import os
from datetime import datetime, timedelta, time
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field

from database import db, create_document

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Time/Calendar Helpers ----------
IST_OFFSET = timedelta(hours=5, minutes=30)
SLOT_MINUTES = 30
START_HOUR_IST = 9
END_HOUR_IST = 17  # exclusive end boundary


def ist_date_from_str(date_str: str) -> datetime:
    try:
        y, m, d = map(int, date_str.split("-"))
        # naive date at midnight IST; we'll treat naive as UTC then add offset where needed
        return datetime(y, m, d)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")


def to_utc_from_ist(date_ist: datetime, t: time) -> datetime:
    dt_ist_naive = datetime.combine(date_ist.date(), t)
    # Convert IST naive to UTC by subtracting offset
    return dt_ist_naive - IST_OFFSET


def overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return a_start < b_end and b_start < a_end


# ---------- Models ----------
class AvailabilityResponse(BaseModel):
    date: str
    slots: List[str]  # list of HH:MM in IST


class BookingRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    phone: Optional[str] = None
    date: str = Field(..., description="YYYY-MM-DD in IST")
    time: str = Field(..., description="HH:MM 24h in IST")
    notes: Optional[str] = None


class BookingResponse(BaseModel):
    status: str
    date: str
    time: str
    timezone: str = "IST"


# ---------- Routes ----------
@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI Backend!"}


@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}


@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"

            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"

    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    import os as _os
    response["database_url"] = "✅ Set" if _os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if _os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response


@app.get("/api/availability", response_model=AvailabilityResponse)
def get_availability(date: str = Query(..., description="YYYY-MM-DD in IST")):
    # Validate date
    date_dt = ist_date_from_str(date)
    # Monday=0, Sunday=6
    weekday = date_dt.weekday()
    if weekday >= 5:
        return AvailabilityResponse(date=date, slots=[])

    # Generate all 30-min slots in IST between 9 and 17 (exclusive of 17:00)
    all_slots_ist: List[str] = []
    current = time(hour=START_HOUR_IST, minute=0)
    while True:
        if current.hour >= END_HOUR_IST or (current.hour == END_HOUR_IST and current.minute > 0):
            break
        all_slots_ist.append(f"{current.hour:02d}:{current.minute:02d}")
        # increment
        dt = datetime.combine(date_dt.date(), current) + timedelta(minutes=SLOT_MINUTES)
        current = time(dt.hour, dt.minute)

    # Remove already booked slots by checking DB overlaps
    taken: set[str] = set()
    col = db["booking"]

    # Compute UTC window for the day to query efficiently
    day_start_utc = to_utc_from_ist(date_dt, time(0, 0))
    day_end_utc = to_utc_from_ist(date_dt + timedelta(days=1), time(0, 0))

    existing = list(col.find({
        "start_utc_iso": {"$gte": day_start_utc.isoformat(), "$lt": day_end_utc.isoformat()}
    }))

    for doc in existing:
        try:
            s = datetime.fromisoformat(doc.get("start_utc_iso"))
            e = datetime.fromisoformat(doc.get("end_utc_iso"))
            # convert back to IST formatted time for marking taken
            ist_start = s + IST_OFFSET
            taken.add(f"{ist_start.hour:02d}:{ist_start.minute:02d}")
        except Exception:
            continue

    available = [slot for slot in all_slots_ist if slot not in taken]
    return AvailabilityResponse(date=date, slots=available)


@app.post("/api/book", response_model=BookingResponse)
def create_booking(payload: BookingRequest):
    # Validate weekday
    date_dt = ist_date_from_str(payload.date)
    if date_dt.weekday() >= 5:
        raise HTTPException(status_code=400, detail="Bookings allowed Monday to Friday only")

    # Validate time format
    try:
        h, m = map(int, payload.time.split(":"))
        t_obj = time(hour=h, minute=m)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid time format. Use HH:MM 24h")

    if not (START_HOUR_IST <= t_obj.hour < END_HOUR_IST):
        raise HTTPException(status_code=400, detail="Time must be between 09:00 and 17:00 IST")

    # Compute UTC times for storage
    start_utc = to_utc_from_ist(date_dt, t_obj)
    end_utc = start_utc + timedelta(minutes=SLOT_MINUTES)

    # Prevent double-booking by checking overlap
    col = db["booking"]
    conflict = col.find_one({
        "$or": [
            {
                "start_utc_iso": {"$lt": end_utc.isoformat()},
                "end_utc_iso": {"$gt": start_utc.isoformat()}
            }
        ]
    })

    if conflict:
        raise HTTPException(status_code=409, detail="This time slot has already been booked. Please choose another.")

    # Persist
    from schemas import Booking as BookingSchema
    booking_doc = BookingSchema(
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        date_ist=payload.date,
        start_time_ist=payload.time,
        start_utc_iso=start_utc.isoformat(),
        end_utc_iso=end_utc.isoformat(),
        notes=payload.notes,
    )

    _id = create_document("booking", booking_doc)

    return BookingResponse(status="confirmed", date=payload.date, time=payload.time)


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
