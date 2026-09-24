"""FastAPI service: trains a gradient-boosted readmission model on synthetic
data at startup and serves cohort risk, what-if predictions and per-factor
contributions. Synthetic data only. Not for clinical use."""
import os
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
load_dotenv()

from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

FEATURES = [
    dict(key="age", label="Age", unit="yrs", min=18, max=95, step=1),
    dict(key="prior_admissions", label="Admissions, past 12 mo", unit="", min=0, max=10, step=1),
    dict(key="ed_visits", label="ED visits, past 6 mo", unit="", min=0, max=8, step=1),
    dict(key="length_of_stay", label="Length of stay", unit="days", min=1, max=30, step=1),
    dict(key="charlson", label="Charlson comorbidity index", unit="", min=0, max=10, step=1),
    dict(key="medications", label="Discharge medications", unit="", min=0, max=25, step=1),
    dict(key="hemoglobin", label="Hemoglobin", unit="g/dL", min=6, max=17, step=0.1),
]
KEYS = [f["key"] for f in FEATURES]
LIMITS = {f["key"]: (f["min"], f["max"]) for f in FEATURES}
LOW, HIGH = 0.20, 0.40  # tier cut-offs on 30-day readmission probability
S = {}
STATIC = Path(os.getenv("STATIC_DIR", Path(__file__).parent / "static"))
CORS = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")


def tier(p: float) -> str:
    return "low" if p < LOW else "moderate" if p < HIGH else "high"


def synth(n: int, seed: int) -> pd.DataFrame:
    r = np.random.default_rng(seed)
    d = pd.DataFrame({
        "age": r.normal(66, 15, n).clip(18, 95).round(),
        "prior_admissions": r.poisson(1.0, n).clip(0, 10),
        "ed_visits": r.poisson(0.8, n).clip(0, 8),
        "length_of_stay": (r.gamma(2, 2.5, n) + 1).clip(1, 30).round(),
        "charlson": r.poisson(2.5, n).clip(0, 10),
        "medications": r.normal(8, 4, n).clip(0, 25).round(),
        "hemoglobin": r.normal(12, 1.8, n).clip(6, 17).round(1),
    })
    z = (-3.1 + 0.018 * (d.age - 66) + 0.30 * d.prior_admissions + 0.20 * d.ed_visits
         + 0.04 * d.length_of_stay + 0.03 * np.maximum(d.length_of_stay - 10, 0)
         + 0.18 * d.charlson + 0.03 * d.medications - 0.15 * (d.hemoglobin - 12)
         + 0.04 * d.prior_admissions * d.charlson)
    d["readmit"] = (r.random(n) < 1 / (1 + np.exp(-z))).astype(int)
    return d


def explain(rows: list[dict]) -> list[dict]:
    """Occlusion attribution: risk(x) minus risk(x with one factor set to the
    cohort mean). Positive = pushes risk up. Works with any sklearn model."""
    out = []
    for x in rows:
        base = pd.DataFrame([x])[KEYS]
        variants = [base]
        for k in KEYS:
            v = base.copy()
            v[k] = S["means"][k]
            variants.append(v)
        p = S["model"].predict_proba(pd.concat(variants))[:, 1]
        out.append(dict(
            risk=float(p[0]), tier=tier(p[0]),
            contributions=[dict(key=k, value=float(p[0] - p[i + 1]))
                           for i, k in enumerate(KEYS)],
        ))
    return out


@asynccontextmanager
async def lifespan(_: FastAPI):
    df = synth(6000, 42)
    Xtr, Xte, ytr, yte = train_test_split(df[KEYS], df.readmit, test_size=0.25, random_state=1)
    model = GradientBoostingClassifier(n_estimators=150, max_depth=3, learning_rate=0.06,
                                       subsample=0.8, random_state=1).fit(Xtr, ytr)
    S.update(model=model, means=df[KEYS].mean().to_dict(),
             auc=float(roc_auc_score(yte, model.predict_proba(Xte)[:, 1])),
             prevalence=float(df.readmit.mean()))
    cohort = synth(120, 7)[KEYS]
    S["cohort"] = []
    for i, x in enumerate(cohort.to_dict("records")):
        e = explain([x])[0]
        top = max(e["contributions"], key=lambda c: c["value"])
        S["cohort"].append(dict(id=f"P-{1001 + i}", features=x, top_driver=top["key"], **e))
    yield


app = FastAPI(title="Readmission Risk API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=CORS, allow_methods=["GET", "POST"], allow_headers=["*"])


class PredictIn(BaseModel):
    features: dict[str, float]


@app.get("/api/meta")
def meta():
    return dict(features=FEATURES, means=S["means"], tiers=dict(low=LOW, high=HIGH),
                auc=round(S["auc"], 3), prevalence=round(S["prevalence"], 3))


@app.get("/api/cohort")
def cohort():
    return sorted(S["cohort"], key=lambda p: -p["risk"])


@app.post("/api/predict")
def predict(body: PredictIn):
    missing = [k for k in KEYS if k not in body.features]
    if missing:
        raise HTTPException(422, f"Missing factors: {', '.join(missing)}")
    x = {k: min(max(body.features[k], LIMITS[k][0]), LIMITS[k][1]) for k in KEYS}
    return explain([x])[0]


@app.get("/api/health")
def health():
    return {"status": "ok", "model_ready": "model" in S}

class ExplainIn(BaseModel):
    patient: dict
    prediction: dict
    risk_factors: list

@app.post("/api/risk/explain")
def risk_explain(body: ExplainIn):
    try:
        from services.groq_service import explain_risk
        explanation = explain_risk(body.model_dump())
        return explanation
    except Exception as e:
        raise HTTPException(500, str(e))

class ChatIn(BaseModel):
    patient: dict
    prediction: dict
    risk_factors: list
    messages: list

@app.post("/api/risk/chat")
def risk_chat(body: ChatIn):
    try:
        from services.groq_service import chat_risk
        reply = chat_risk(body.model_dump())
        return {"reply": reply}
    except Exception as e:
        raise HTTPException(500, str(e))

# Serve the built Vue app from the same origin (registered last so /api wins).
if STATIC.is_dir():
    app.mount("/", StaticFiles(directory=STATIC, html=True), name="ui")
