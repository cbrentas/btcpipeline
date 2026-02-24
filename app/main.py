from fastapi import FastAPI, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from app.db import SessionLocal
from app.models import Price
from scripts.model import compute_sma
import os
from dotenv import load_dotenv
from fastapi.staticfiles import StaticFiles
from fastapi import Request
from scripts.model import compute_sma, predict_next
from scripts.model import compute_sma, predict_next, compute_volatility, get_history
from sqlalchemy import func
from app.models import Price, Prediction, ModelState

load_dotenv()

API_KEY = os.getenv("API_KEY")
 
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/dashboard", StaticFiles(directory="app/static", html=True), name="static")


# ---- DB dependency ----
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---- Simple API key guard ----
def check_api_key(request: Request, x_api_key: str = Header(None)):
    client_ip = request.client.host


    # Allow requests coming from same server (dashboard)
    if client_ip == "127.0.0.1":
        return

    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/metrics")
def metrics(request: Request, db: Session = Depends(get_db)):

    print("ENTER METRICS")

    latest = (
        db.query(Price)
        .order_by(Price.timestamp.desc())
        .first()
    )

    if not latest:
        raise HTTPException(status_code=404)

    sma = compute_sma()
    prediction = predict_next()
    volatility = compute_volatility()
    history = get_history()


    return {
        "symbol": latest.symbol,
        "latest_price": float(latest.price_usd),
        "timestamp": latest.timestamp,
        "sma": sma,
        "prediction": prediction,
        "volatility": volatility,
        "history": history
    }

@app.get("/model/summary")
def model_summary(db: Session = Depends(get_db)):
    state = db.query(ModelState).filter(ModelState.id == 1).first()

    last_pred = (
        db.query(Prediction)
        .order_by(Prediction.created_at.desc())
        .first()
    )

    # Only scored predictions
    scored_q = db.query(Prediction).filter(Prediction.y_true.isnot(None))

    # Rolling metrics
    def rolling_mae(limit: int):
        rows = (
            scored_q
            .order_by(Prediction.observed_timestamp.desc())
            .limit(limit)
            .all()
        )
        if not rows:
            return None, None
        mae = float(sum(r.abs_error for r in rows if r.abs_error is not None) / len(rows))
        bmae = float(sum(r.baseline_abs_error for r in rows if r.baseline_abs_error is not None) / len(rows))
        return mae, bmae

    mae_50, bmae_50 = rolling_mae(50)
    mae_200, bmae_200 = rolling_mae(200)

    # Trend: compare last 50 vs previous 50
    trend = None
    if scored_q.count() >= 100:
        last50 = (
            scored_q.order_by(Prediction.observed_timestamp.desc()).limit(50).all()
        )
        prev50 = (
            scored_q.order_by(Prediction.observed_timestamp.desc()).offset(50).limit(50).all()
        )
        last_mae = float(sum(r.abs_error for r in last50 if r.abs_error is not None) / len(last50))
        prev_mae = float(sum(r.abs_error for r in prev50 if r.abs_error is not None) / len(prev50))
        if last_mae < prev_mae:
            trend = "improving"
        elif last_mae > prev_mae:
            trend = "worsening"
        else:
            trend = "flat"

    # "Is it good?" -> does it beat baseline on last 50
    beats_baseline_50 = None
    if mae_50 is not None and bmae_50 is not None:
        beats_baseline_50 = mae_50 < bmae_50

    return {
        "model_version": state.model_version if state else "unknown",
        "model_path": state.model_path if state else None,
        "window_size": state.window_size if state else None,
        "ingest_interval_minutes": state.ingest_interval_minutes if state else None,
        "last_trained_at": state.last_trained_at.isoformat() if state and state.last_trained_at else None,
        "last_processed_price_id": state.last_processed_price_id if state else None,
        "rolling_mae_50": mae_50,
        "rolling_baseline_mae_50": bmae_50,
        "rolling_mae_200": mae_200,
        "rolling_baseline_mae_200": bmae_200,
        "trend": trend,
        "beats_baseline_50": beats_baseline_50,
        "last_prediction": None if not last_pred else {
            "created_at": last_pred.created_at.isoformat(),
            "based_on_timestamp": last_pred.based_on_timestamp.isoformat(),
            "y_pred": last_pred.y_pred,
            "baseline_pred": last_pred.baseline_pred,
            "y_true": last_pred.y_true,
            "abs_error": last_pred.abs_error,
            "baseline_abs_error": last_pred.baseline_abs_error,
        }
    }


@app.get("/model/history")
def model_history(limit: int = 200, db: Session = Depends(get_db)):
    rows = (
        db.query(Prediction)
        .order_by(Prediction.created_at.desc())
        .limit(limit)
        .all()
    )
    rows = list(reversed(rows))  # oldest -> newest for charting

    return [
        {
            "created_at": r.created_at.isoformat(),
            "based_on_timestamp": r.based_on_timestamp.isoformat(),
            "observed_timestamp": r.observed_timestamp.isoformat() if r.observed_timestamp else None,
            "y_pred": r.y_pred,
            "baseline_pred": r.baseline_pred,
            "y_true": r.y_true,
            "abs_error": r.abs_error,
            "baseline_abs_error": r.baseline_abs_error,
        }
        for r in rows
    ]