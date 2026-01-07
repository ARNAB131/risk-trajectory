from sqlalchemy import Column, Integer, String, Float, DateTime, Text
from sqlalchemy.sql import func
from .db import Base

class Patient(Base):
    __tablename__ = "patients"
    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    profile = Column(String, nullable=False)  # normal, hypertensive, athlete, critical
    age = Column(Integer, nullable=True)

class VitalRecord(Base):
    __tablename__ = "vitals"
    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(String, index=True, nullable=False)
    ts = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    heart_rate = Column(Float, nullable=False)
    bp_systolic = Column(Float, nullable=False)
    bp_diastolic = Column(Float, nullable=False)
    oxygen_saturation = Column(Float, nullable=False)
    temperature = Column(Float, nullable=False)

class EventLog(Base):
    __tablename__ = "events"
    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(String, index=True, nullable=False)
    ts = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    level = Column(String, nullable=False)   # green/yellow/orange/red
    title = Column(String, nullable=False)   # e.g. "CRITICAL ALERT"
    message = Column(Text, nullable=False)   # explainability summary
    payload_json = Column(Text, nullable=True)  # store details as JSON string
