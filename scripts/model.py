from app.db import SessionLocal
from app.models import Price
import numpy as np
from sklearn.linear_model import LinearRegression


def compute_sma(window=10):
    db = SessionLocal()

    rows = (
        db.query(Price.price_usd)
        .order_by(Price.timestamp.desc())
        .limit(window)
        .all()
    )

    db.close()

    values = [float(r[0]) for r in rows]
    return sum(values) / len(values)


def predict_next():
    db = SessionLocal()

    rows = (
        db.query(Price.price_usd)
        .order_by(Price.timestamp.asc())
        .all()
    )

    db.close()

    if len(rows) < 10:
        return None

    y = np.array([float(r[0]) for r in rows[-20:]])
    X = np.arange(len(y)).reshape(-1, 1)

    model = LinearRegression()
    model.fit(X, y)

    next_x = np.array([[len(y)]])
    prediction = model.predict(next_x)[0]

    return float(prediction)


def compute_volatility(window=10):
    db = SessionLocal()
    rows = (
        db.query(Price.price_usd)
        .order_by(Price.timestamp.desc())
        .limit(window)
        .all()
    )
    db.close()

    values = np.array([float(r[0]) for r in rows])

    if len(values) < 2:
        return None

    return float(np.std(values))


def get_history(limit=50):
    db = SessionLocal()
    rows = (
        db.query(Price.timestamp, Price.price_usd)
        .order_by(Price.timestamp.asc())
        .limit(limit)
        .all()
    )
    db.close()

    return [
        {"t": r[0].isoformat(), "p": float(r[1])}
        for r in rows
    ]