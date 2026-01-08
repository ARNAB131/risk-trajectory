from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.sql import func
import json

Base = declarative_base()

class VitalRow(Base):
    __tablename__ = "vitals"
    id = Column(Integer, primary_key=True)
    patient_id = Column(String, index=True, nullable=False)
    ts = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    heart_rate = Column(Float, nullable=False)
    bp_systolic = Column(Float, nullable=False)
    bp_diastolic = Column(Float, nullable=False)
    oxygen_saturation = Column(Float, nullable=False)
    temperature = Column(Float, nullable=False)

class EventRow(Base):
    __tablename__ = "events"
    id = Column(Integer, primary_key=True)
    patient_id = Column(String, index=True, nullable=False)
    ts = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    level = Column(String, nullable=False)
    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    payload_json = Column(Text, nullable=True)

def init_db(db_url: str = "sqlite:///risk_trajectory.db"):
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)

def save_vital(Session, patient_id: str, v: dict):
    with Session() as s:
        row = VitalRow(patient_id=patient_id, **v)
        s.add(row)
        s.commit()

def save_event(Session, patient_id: str, level: str, title: str, message: str, payload: dict):
    with Session() as s:
        row = EventRow(
            patient_id=patient_id,
            level=level,
            title=title,
            message=message,
            payload_json=json.dumps(payload, ensure_ascii=False),
        )
        s.add(row)
        s.commit()

def load_events(Session, patient_id: str, limit: int = 50):
    with Session() as s:
        q = (
            s.query(EventRow)
             .filter(EventRow.patient_id == patient_id)
             .order_by(EventRow.ts.desc())
             .limit(limit)
        )
        rows = q.all()
        out = []
        for r in rows:
            out.append({
                "ts": r.ts.isoformat() if r.ts else "",
                "level": r.level,
                "title": r.title,
                "message": r.message,
            })
        return out
