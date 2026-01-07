from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import select, desc
import json
import time
import asyncio
import os
import requests

from .db import Base, engine, get_db
from .models import Patient, VitalRecord, EventLog
from .risk_engine import RollingWindow, patient_thresholds, classify_level, infer_outcomes
from .simulator import generate_vitals

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Risk Trajectory API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("WS_ORIGIN", "*")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

NOTIFY_URL = os.getenv("NOTIFY_URL", "http://localhost:4567/notify")

# In-memory windows per patient for trend detection
windows = {}
sim_states = {}

def seed_patients(db: Session):
    existing = db.execute(select(Patient)).scalars().first()
    if existing:
        return
    patients = [
        Patient(id="P001", name="Patient 001", profile="normal", age=45),
        Patient(id="P002", name="Patient 002", profile="hypertensive", age=62),
        Patient(id="P003", name="Patient 003", profile="athlete", age=23),
        Patient(id="P004", name="Patient 004", profile="critical", age=70),
    ]
    db.add_all(patients)
    db.commit()

@app.on_event("startup")
def startup():
    with next(get_db()) as db:
        seed_patients(db)

def log_event(db: Session, patient_id: str, level: str, title: str, message: str, payload: dict):
    ev = EventLog(
        patient_id=patient_id,
        level=level,
        title=title,
        message=message,
        payload_json=json.dumps(payload, ensure_ascii=False),
    )
    db.add(ev)
    db.commit()

def maybe_notify(patient_id: str, level: str, payload: dict):
    # Notify only for orange/red by default
    if level not in ("orange", "red"):
        return
    try:
        requests.post(
            NOTIFY_URL,
            json={
                "patient_id": patient_id,
                "level": level,
                "title": payload.get("title", "Risk Trajectory Alert"),
                "message": payload.get("explain", ""),
                "payload": payload,
            },
            timeout=1.5,
        )
    except Exception:
        # Do not crash monitoring if notify service is down
        pass

@app.get("/patients")
def get_patients(db: Session = Depends(get_db)):
    pts = db.execute(select(Patient)).scalars().all()
    return [{"id": p.id, "name": p.name, "profile": p.profile, "age": p.age} for p in pts]

@app.get("/events")
def get_events(patient_id: str = Query(...), limit: int = 50, db: Session = Depends(get_db)):
    q = select(EventLog).where(EventLog.patient_id == patient_id).order_by(desc(EventLog.ts)).limit(limit)
    events = db.execute(q).scalars().all()
    return [{
        "ts": e.ts.isoformat(),
        "level": e.level,
        "title": e.title,
        "message": e.message,
        "payload": json.loads(e.payload_json) if e.payload_json else None
    } for e in events]

@app.get("/latest")
def get_latest(patient_id: str = Query(...), db: Session = Depends(get_db)):
    q = select(VitalRecord).where(VitalRecord.patient_id == patient_id).order_by(desc(VitalRecord.ts)).limit(1)
    r = db.execute(q).scalars().first()
    if not r:
        return None
    return {
        "ts": r.ts.isoformat(),
        "heart_rate": r.heart_rate,
        "bp_systolic": r.bp_systolic,
        "bp_diastolic": r.bp_diastolic,
        "oxygen_saturation": r.oxygen_saturation,
        "temperature": r.temperature,
    }

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket, patient_id: str):
    await ws.accept()
    # ensure patient exists
    db = next(get_db())
    try:
        p = db.get(Patient, patient_id)
        if not p:
            await ws.send_text(json.dumps({"error": "Unknown patient_id"}))
            await ws.close()
            return

        if patient_id not in windows:
            windows[patient_id] = RollingWindow(maxlen=120)
        if patient_id not in sim_states:
            sim_states[patient_id] = {}

        # main loop: generate, evaluate, persist, stream
        while True:
            vitals = generate_vitals(p.profile, sim_states[patient_id])
            t = time.time()
            windows[patient_id].push(t, vitals)
            rates = windows[patient_id].rates_per_min()

            th = patient_thresholds(p.profile)
            level, reasons, score = classify_level(vitals, th, rates)
            outcomes = infer_outcomes(vitals, level, reasons)

            # persist vitals
            vr = VitalRecord(
                patient_id=patient_id,
                heart_rate=vitals["heart_rate"],
                bp_systolic=vitals["bp_systolic"],
                bp_diastolic=vitals["bp_diastolic"],
                oxygen_saturation=vitals["oxygen_saturation"],
                temperature=vitals["temperature"],
            )
            db.add(vr)
            db.commit()

            # log event on meaningful conditions
            title = {
                "green": "Stable",
                "yellow": "Warning",
                "orange": "High Risk",
                "red": "CRITICAL ALERT",
            }[level]

            explain = " | ".join(reasons[:4]) if reasons else "No abnormalities detected."

            payload = {
                "patient_id": patient_id,
                "profile": p.profile,
                "level": level,
                "risk_score": round(score, 1),
                "vitals": vitals,
                "rates_per_min": {k: round(v, 2) for k, v in rates.items()},
                "outcomes": outcomes,
                "explain": explain,
                "title": title,
            }

            # Only log when yellow+ or score significant, to keep DB clean.
            if level in ("yellow", "orange", "red"):
                log_event(db, patient_id, level, title, explain, payload)
                maybe_notify(patient_id, level, payload)

            await ws.send_text(json.dumps(payload))

            await asyncio.sleep(1.0)

    except WebSocketDisconnect:
        return
    finally:
        db.close()
