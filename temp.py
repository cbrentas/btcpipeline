from app.db import SessionLocal
from app.models import Price

db = SessionLocal()
print("Total price rows:", db.query(Price).count())
rows = db.query(Price).order_by(Price.id.desc()).limit(5).all()
for r in rows:
    print(r.id, r.timestamp, float(r.price_usd))
db.close()
exit()