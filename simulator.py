import random
from typing import Dict

def _clamp(x, lo, hi):
    return max(lo, min(hi, x))

def generate_vitals(profile: str, state: Dict) -> Dict[str, float]:
    """
    Generates semi-realistic vitals with continuity using 'state'.
    """
    if not state:
        if profile == "athlete":
            state.update({"hr": 62, "sys": 118, "dia": 74, "spo2": 98, "temp": 36.6})
        elif profile == "hypertensive":
            state.update({"hr": 82, "sys": 148, "dia": 96, "spo2": 97, "temp": 36.8})
        elif profile == "critical":
            state.update({"hr": 98, "sys": 140, "dia": 92, "spo2": 95, "temp": 37.4})
        else:
            state.update({"hr": 78, "sys": 124, "dia": 80, "spo2": 98, "temp": 36.7})

    # random walk
    state["hr"] += random.uniform(-2.5, 2.5)
    state["sys"] += random.uniform(-3.0, 3.0)
    state["dia"] += random.uniform(-2.0, 2.0)
    state["spo2"] += random.uniform(-0.6, 0.4)
    state["temp"] += random.uniform(-0.05, 0.05)

    # occasional deterioration
    if random.random() < 0.02:
        state["hr"] += random.uniform(10, 25)
        state["sys"] += random.uniform(15, 35)
        state["dia"] += random.uniform(10, 20)

    if random.random() < 0.02:
        state["spo2"] -= random.uniform(2, 6)

    if random.random() < 0.01:
        state["temp"] += random.uniform(0.6, 1.2)

    # clamp
    state["hr"] = _clamp(state["hr"], 40, 190)
    state["sys"] = _clamp(state["sys"], 90, 220)
    state["dia"] = _clamp(state["dia"], 50, 140)
    state["spo2"] = _clamp(state["spo2"], 75, 100)
    state["temp"] = _clamp(state["temp"], 34.0, 41.0)

    return {
        "heart_rate": float(round(state["hr"], 1)),
        "bp_systolic": float(round(state["sys"], 1)),
        "bp_diastolic": float(round(state["dia"], 1)),
        "oxygen_saturation": float(round(state["spo2"], 1)),
        "temperature": float(round(state["temp"], 2)),
    }
