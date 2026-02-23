import requests
from dotenv import load_dotenv
from app.db import SessionLocal
from app.models import Price

load_dotenv()


def fetch_price():
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {
        "ids": "bitcoin",
        "vs_currencies": "usd"
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()
    return data["bitcoin"]["usd"]


def insert_price(price):
    db = SessionLocal()

    row = Price(
        symbol="BTC",
        price_usd=price
    )

    db.add(row)
    db.commit()
    db.close()


if __name__ == "__main__":
    price = fetch_price()
    insert_price(price)
    print("Inserted BTC price:", price)