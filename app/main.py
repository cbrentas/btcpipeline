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