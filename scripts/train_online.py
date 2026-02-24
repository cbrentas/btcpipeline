import os
from datetime import datetime
from dotenv import load_dotenv
from datetime import timedelta

import numpy as np
from sklearn.linear_model import LinearRegression
import joblib

from app.db import SessionLocal
from app.models import Price, Prediction, ModelState



load_dotenv()

DEFAULT_MODEL_VERSION = "lr_window_v1"


def ensure_dirs(path: str) -> None:
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)


def get_or_create_state(db) -> ModelState:
    state = db.query(ModelState).filter(ModelState.id == 1).first()
    if not state:
        state = ModelState(
            id=1,
            last_processed_price_id=0,
            last_trained_at=None,
            model_version=DEFAULT_MODEL_VERSION,
            model_path="models/lr_window_v1.joblib",
            ingest_interval_minutes=5,
            window_size=200,
            allow_untrained_predictions=True,
        )
        db.add(state)
        db.commit()
        db.refresh(state)
    return state


def load_model_if_exists(model_path: str):
    if os.path.exists(model_path):
        try:
            return joblib.load(model_path)
        except Exception:
            return None
    return None


def fit_window_lr(prices: list[float]) -> LinearRegression:
    """
    Fit LinearRegression on last window prices using simple index feature.
    """
    y = np.array(prices, dtype=float)
    X = np.arange(len(y), dtype=float).reshape(-1, 1)

    model = LinearRegression()
    model.fit(X, y)
    return model


def predict_next_from_model(model: LinearRegression, window_len: int) -> float:
    next_x = np.array([[float(window_len)]])
    return float(model.predict(next_x)[0])


def score_oldest_pending_prediction(db, new_price_row: Price) -> None:
    """
    When a new real price arrives, score the oldest prediction with y_true is NULL.
    This implements predict-then-learn evaluation (prequential).
    """
    pending = (
        db.query(Prediction)
        .filter(Prediction.y_true.is_(None))
        .order_by(Prediction.created_at.asc())
        .first()
    )
    if not pending:
        return

    y_true = float(new_price_row.price_usd)
    pending.y_true = y_true
    pending.observed_price_id = new_price_row.id
    pending.observed_timestamp = new_price_row.timestamp

    pending.abs_error = float(abs(pending.y_pred - y_true))
    pending.baseline_abs_error = float(abs(pending.baseline_pred - y_true))

    db.add(pending)


def create_new_prediction(db, state: ModelState, latest_price_row: Price, model) -> None:
    """
    Create a prediction "for the next step".
    Baseline: next price = current price.
    Model pred: if trained model exists, use it, else baseline.
    """
    latest_price = float(latest_price_row.price_usd)
    baseline_pred = latest_price

    y_pred = baseline_pred
    trained_on_n = 0

    # Try model prediction if we have a model object
    if model is not None:
        # Fetch last window prices to determine window_len used for X indexing
        window_rows = (
            db.query(Price.price_usd)
            .order_by(Price.timestamp.desc())
            .limit(state.window_size)
            .all()
        )
        window_prices = [float(r[0]) for r in reversed(window_rows)]  # oldest -> newest
        if len(window_prices) >= 20:
            y_pred = predict_next_from_model(model, window_len=len(window_prices))
            trained_on_n = len(window_prices)

    pred = Prediction(
        created_at=datetime.utcnow(),
        based_on_price_id=latest_price_row.id,
        based_on_timestamp=latest_price_row.timestamp,
        y_pred=float(y_pred),
        baseline_pred=float(baseline_pred),
        model_version=state.model_version,
        window_size=state.window_size,
        trained_on_n=trained_on_n,
    )
    db.add(pred)


def maybe_train_and_save_model(db, state: ModelState) -> LinearRegression | None:
    """
    Train on a rolling window, but at most once every 30 minutes.
    Always returns the best available model (newly trained or previously saved).
    """
    # If we trained recently, just reuse the last saved model
    if state.last_trained_at is not None:
        if datetime.utcnow() - state.last_trained_at < timedelta(minutes=30):
            return load_model_if_exists(state.model_path)

    # Otherwise, try to train a fresh model on the rolling window
    rows = (
        db.query(Price.price_usd)
        .order_by(Price.timestamp.desc())
        .limit(state.window_size)
        .all()
    )
    prices = [float(r[0]) for r in reversed(rows)]  # oldest -> newest

    if len(prices) < 30:
        # Not enough data to train; fallback to any existing model on disk
        return load_model_if_exists(state.model_path)

    model = fit_window_lr(prices)

    ensure_dirs(state.model_path)
    joblib.dump(model, state.model_path)

    state.last_trained_at = datetime.utcnow()
    db.add(state)

    return model


def main():
    db = SessionLocal()
    try:
        state = get_or_create_state(db)

        # 1) Get new prices since last_processed_price_id
        new_rows = (
            db.query(Price)
            .filter(Price.id > state.last_processed_price_id)
            .order_by(Price.id.asc())
            .all()
        )

        if not new_rows:
            print("No new prices. Exiting.")
            return

        # Load existing model if exists
        model = load_model_if_exists(state.model_path)

        # 2) For each new price: score pending prediction
        for row in new_rows:
            score_oldest_pending_prediction(db, row)
            state.last_processed_price_id = row.id
            db.add(state)

        db.commit()

        # 3) Train (rolling window) after processing new points
        model = maybe_train_and_save_model(db, state)
        db.commit()

        # 4) Create a new prediction based on the latest row
        latest_row = new_rows[-1]

        # If model is None and we don't allow untrained predictions, skip
        if model is None and not state.allow_untrained_predictions:
            print("Model not trained yet; skipping prediction creation.")
            db.commit()
            return

        create_new_prediction(db, state, latest_row, model)
        db.commit()

        print(
            f"Processed prices up to id={state.last_processed_price_id}. "
            f"Prediction created based on price id={latest_row.id}."
        )

    finally:
        db.close()


if __name__ == "__main__":
    main()