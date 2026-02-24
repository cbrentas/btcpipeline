from sqlalchemy import Column, Integer, String, Numeric, DateTime, Float, Boolean
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()

class Price(Base):
    __tablename__ = "prices"

    id = Column(Integer, primary_key=True)
    symbol = Column(String)
    price_usd = Column(Numeric)
    timestamp = Column(DateTime, default=datetime.utcnow)


class Prediction(Base):
    """
    One prediction per step.
    We score it later when the next real price arrives.
    """
    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Which price row triggered this prediction
    based_on_price_id = Column(Integer, nullable=False)
    based_on_timestamp = Column(DateTime, nullable=False)

    # When we later observe the real price, we fill these
    observed_price_id = Column(Integer, nullable=True)
    observed_timestamp = Column(DateTime, nullable=True)

    y_pred = Column(Float, nullable=False)
    baseline_pred = Column(Float, nullable=False)  # naive baseline: "next = current"

    y_true = Column(Float, nullable=True)

    abs_error = Column(Float, nullable=True)
    baseline_abs_error = Column(Float, nullable=True)

    model_version = Column(String, nullable=False, default="lr_window_v1")
    window_size = Column(Integer, nullable=False, default=200)
    trained_on_n = Column(Integer, nullable=False, default=0)


class ModelState(Base):
    """
    Singleton table (we'll keep id=1) that tracks progress.
    """
    __tablename__ = "model_state"

    id = Column(Integer, primary_key=True)  # use 1
    last_processed_price_id = Column(Integer, nullable=False, default=0)
    last_trained_at = Column(DateTime, nullable=True)

    model_version = Column(String, nullable=False, default="lr_window_v1")
    model_path = Column(String, nullable=False, default="models/lr_window_v1.joblib")

    ingest_interval_minutes = Column(Integer, nullable=False, default=5)
    window_size = Column(Integer, nullable=False, default=200)

    # If True, we create predictions even if we haven't trained yet (we will, once enough data exists)
    allow_untrained_predictions = Column(Boolean, nullable=False, default=True)