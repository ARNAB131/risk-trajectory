from dataclasses import dataclass
from collections import deque
from typing import Dict, Any, List, Tuple
import time

@dataclass
class Thresholds:
    hr_red: float
    spo2_red: float
    sys_red: float
    dia_red: float
    temp_red_hi: float
    temp_red_lo: float

    hr_yellow: float
    spo2_yellow: float
    sys_yellow: float
    dia_yellow: float
    temp_yellow_hi: float
    temp_yellow_lo: float

def patient_thresholds(profile: str) -> Thresholds:
    if profile == "athlete":
        return Thresholds(
            hr_red=140, spo2_red=92, sys_red=170, dia_red=110, temp_red_hi=39.0, temp_red_lo=35.0,
            hr_yellow=105, spo2_yellow=95, sys_yellow=145, dia_yellow=95, temp_yellow_hi=38.0, temp_yellow_lo=36.0
        )
    if profile == "hypertensive":
        return Thresholds(
            hr_red=150, spo2_red=92, sys_red=180, dia_red=120, temp_red_hi=39.0, temp_red_lo=35.0,
            hr_yellow=110, spo2_yellow=95, sys_yellow=155, dia_yellow=100, temp_yellow_hi=38.0, temp_yellow_lo=36.0
        )
    if profile == "critical":
        return Thresholds(
            hr_red=135, spo2_red=90, sys_red=165, dia_red=105, temp_red_hi=39.0, temp_red_lo=35.0,
            hr_yellow=105, spo2_yellow=94, sys_yellow=145, dia_yellow=95, temp_yellow_hi=38.0, temp_yellow_lo=36.0
        )
    return Thresholds(
        hr_red=150, spo2_red=92, sys_red=170, dia_red=110, temp_red_hi=39.0, temp_red_lo=35.0,
        hr_yellow=110, spo2_yellow=95, sys_yellow=150, dia_yellow=95, temp_yellow_hi=38.0, temp_yellow_lo=36.0
    )

class RollingWindow:
    def __init__(self, maxlen: int = 120):
        self.data = deque(maxlen=maxlen)  # (t_epoch, vitals)

    def push(self, vitals: Dict[str, float], t_epoch: float | None = None):
        self.data.append((t_epoch or time.time(), vitals))

    def _rate_per_min(self, key: str, seconds: float) -> float:
        if len(self.data) < 2:
            return 0.0
        t_now, v_now = self.data[-1]
        t_ref, v_ref = self.data[0]
        for t_i, v_i in self.data:
            if t_now - t_i >= seconds:
                t_ref, v_ref = t_i, v_i
                break
        dt = max(1e-6, t_now - t_ref)
        return (v_now[key] - v_ref[key]) / dt * 60.0

    def rates_per_min(self) -> Dict[str, float]:
        return {
            "heart_rate": self._rate_per_min("heart_rate", 60.0),
            "bp_systolic": self._rate_per_min("bp_systolic", 120.0),
            "oxygen_saturation": self._rate_per_min("oxygen_saturation", 60.0),
            "temperature": self._rate_per_min("temperature", 300.0),
        }

def classify_level(v: Dict[str, float], th: Thresholds, rates: Dict[str, float]) -> Tuple[str, List[str], float]:
    reasons: List[str] = []
    score = 0.0
    red_hits = 0
    warn_hits = 0

    # RED thresholds
    if v["heart_rate"] >= th.hr_red:
        red_hits += 1; score += 25
        reasons.append(f"HR {v['heart_rate']:.0f} >= {th.hr_red:.0f}")
    if v["oxygen_saturation"] <= th.spo2_red:
        red_hits += 1; score += 30
        reasons.append(f"SpO2 {v['oxygen_saturation']:.0f}% <= {th.spo2_red:.0f}%")
    if v["bp_systolic"] >= th.sys_red or v["bp_diastolic"] >= th.dia_red:
        red_hits += 1; score += 25
        reasons.append(f"BP {v['bp_systolic']:.0f}/{v['bp_diastolic']:.0f} >= {th.sys_red:.0f}/{th.dia_red:.0f}")
    if v["temperature"] >= th.temp_red_hi or v["temperature"] <= th.temp_red_lo:
        red_hits += 1; score += 15
        reasons.append(f"Temp {v['temperature']:.1f} outside [{th.temp_red_lo:.1f},{th.temp_red_hi:.1f}]")

    # Trend boosts
    if rates["heart_rate"] >= 15:
        score += 10; reasons.append(f"HR rising fast (+{rates['heart_rate']:.1f}/min)")
    if rates["oxygen_saturation"] <= -2:
        score += 15; reasons.append(f"SpO2 dropping (-{abs(rates['oxygen_saturation']):.1f}/min)")
    if rates["bp_systolic"] >= 10:
        score += 10; reasons.append(f"Systolic rising (+{rates['bp_systolic']:.1f}/min)")

    # Yellow thresholds
    if v["heart_rate"] >= th.hr_yellow:
        warn_hits += 1; score += 8
        reasons.append(f"HR {v['heart_rate']:.0f} >= {th.hr_yellow:.0f} (warning)")
    if v["oxygen_saturation"] <= th.spo2_yellow:
        warn_hits += 1; score += 10
        reasons.append(f"SpO2 {v['oxygen_saturation']:.0f}% <= {th.spo2_yellow:.0f}% (warning)")
    if v["bp_systolic"] >= th.sys_yellow or v["bp_diastolic"] >= th.dia_yellow:
        warn_hits += 1; score += 8
        reasons.append(f"BP {v['bp_systolic']:.0f}/{v['bp_diastolic']:.0f} elevated (warning)")
    if v["temperature"] >= th.temp_yellow_hi or v["temperature"] <= th.temp_yellow_lo:
        warn_hits += 1; score += 6
        reasons.append(f"Temp {v['temperature']:.1f} abnormal (warning)")

    score = max(0.0, min(100.0, score))

    if red_hits >= 1 and score >= 55:
        return "red", reasons, score
    if red_hits >= 1 or score >= 45 or warn_hits >= 2:
        return "orange", reasons, score
    if warn_hits >= 1 or score >= 20:
        return "yellow", reasons, score
    return "green", reasons, score

def infer_outcomes(v: Dict[str, float], level: str, reasons: List[str]) -> List[Dict[str, Any]]:
    outcomes: List[Dict[str, Any]] = []

    if v["heart_rate"] >= 130 and (v["bp_systolic"] >= 170 or v["oxygen_saturation"] <= 92):
        outcomes.append({
            "name": "Acute cardiac event risk",
            "probability": 0.75 if level == "red" else 0.55,
            "because": ["High HR with high BP or low SpO2"] + reasons[:2],
            "action": "Immediate clinician review; ECG + troponin; oxygen support if needed."
        })

    if v["bp_systolic"] >= 180 or v["bp_diastolic"] >= 120:
        outcomes.append({
            "name": "Stroke / hypertensive crisis risk",
            "probability": 0.80 if level in ("orange", "red") else 0.60,
            "because": ["Severely elevated blood pressure"] + reasons[:2],
            "action": "Urgent BP management; neuro checks; emergency protocol if needed."
        })

    if v["oxygen_saturation"] <= 90:
        outcomes.append({
            "name": "Respiratory compromise risk",
            "probability": 0.85 if level == "red" else 0.65,
            "because": ["Low oxygen saturation"] + reasons[:2],
            "action": "Check airway; oxygen; evaluate pulmonary causes."
        })

    if v["temperature"] >= 38.5 and v["heart_rate"] >= 120:
        outcomes.append({
            "name": "Systemic infection / sepsis risk (screen)",
            "probability": 0.60 if level in ("orange", "red") else 0.40,
            "because": ["Fever + tachycardia pattern"] + reasons[:2],
            "action": "Clinical assessment; labs; fluids per protocol if indicated."
        })

    if not outcomes and level in ("orange", "red"):
        outcomes.append({
            "name": "Undifferentiated deterioration risk",
            "probability": 0.50,
            "because": reasons[:3],
            "action": "Repeat vitals; verify sensors; clinician evaluation."
        })

    return outcomes
