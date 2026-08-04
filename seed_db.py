"""
seed_db.py
Creates a small e-commerce-style schema (customers, products, orders,
order_items) and populates it with synthetic data, so the agent has a
realistic database to query out of the box.

Run with:
    python seed_db.py
"""

import os
import random
from datetime import date, timedelta

import psycopg2
from dotenv import load_dotenv

load_dotenv()

PG_HOST     = os.getenv("PG_HOST", "localhost")
PG_PORT     = int(os.getenv("PG_PORT", 5432))
PG_DB       = os.getenv("PG_DB", "analyst_demo")
PG_USER     = os.getenv("PG_USER", "postgres")
PG_PASSWORD = os.getenv("PG_PASSWORD", "postgres")

SCHEMA_SQL = """
DROP TABLE IF EXISTS order_items CASCADE;
DROP TABLE IF EXISTS orders CASCADE;
DROP TABLE IF EXISTS products CASCADE;
DROP TABLE IF EXISTS customers CASCADE;

CREATE TABLE customers (
    customer_id SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    region      TEXT NOT NULL,
    signup_date DATE NOT NULL
);

CREATE TABLE products (
    product_id SERIAL PRIMARY KEY,
    name       TEXT NOT NULL,
    category   TEXT NOT NULL,
    price      NUMERIC(10,2) NOT NULL
);

CREATE TABLE orders (
    order_id    SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    order_date  DATE NOT NULL,
    status      TEXT NOT NULL
);

CREATE TABLE order_items (
    order_item_id SERIAL PRIMARY KEY,
    order_id      INTEGER NOT NULL REFERENCES orders(order_id),
    product_id    INTEGER NOT NULL REFERENCES products(product_id),
    quantity      INTEGER NOT NULL,
    unit_price    NUMERIC(10,2) NOT NULL
);
"""

REGIONS = ["Northeast", "Southeast", "Midwest", "Southwest", "West"]
CATEGORIES = {
    "Electronics": ["Wireless Mouse", "Mechanical Keyboard", "USB-C Hub", "Webcam", "Monitor Stand"],
    "Home": ["Ceramic Mug Set", "Throw Blanket", "Desk Lamp", "Candle", "Wall Clock"],
    "Apparel": ["Cotton T-Shirt", "Running Shoes", "Wool Sweater", "Rain Jacket", "Baseball Cap"],
    "Books": ["Mystery Novel", "Cookbook", "Biography", "Sci-Fi Anthology", "Travel Guide"],
}
STATUSES = ["completed", "completed", "completed", "completed", "cancelled", "refunded"]

FIRST_NAMES = ["Alex", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Sam", "Jamie",
               "Avery", "Quinn", "Drew", "Reese", "Skyler", "Cameron", "Rowan"]
LAST_NAMES = ["Nguyen", "Patel", "Garcia", "Smith", "Kim", "Johnson", "Chen", "Brown",
              "Martinez", "Lee", "Davis", "Wilson", "Anderson", "Taylor", "Thomas"]


def random_date(start: date, end: date) -> date:
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, delta))


def main():
    conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, dbname=PG_DB, user=PG_USER, password=PG_PASSWORD)
    cur = conn.cursor()

    print("Creating schema…")
    cur.execute(SCHEMA_SQL)

    print("Seeding customers…")
    customer_ids = []
    for _ in range(200):
        name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
        region = random.choice(REGIONS)
        signup = random_date(date(2023, 1, 1), date(2025, 6, 1))
        cur.execute(
            "INSERT INTO customers (name, region, signup_date) VALUES (%s,%s,%s) RETURNING customer_id",
            (name, region, signup),
        )
        customer_ids.append(cur.fetchone()[0])

    print("Seeding products…")
    product_ids = {}
    for category, names in CATEGORIES.items():
        for name in names:
            price = round(random.uniform(8, 150), 2)
            cur.execute(
                "INSERT INTO products (name, category, price) VALUES (%s,%s,%s) RETURNING product_id",
                (name, category, price),
            )
            product_ids[cur.fetchone()[0]] = price

    print("Seeding orders + order_items…")
    for _ in range(1200):
        cust = random.choice(customer_ids)
        odate = random_date(date(2024, 1, 1), date(2026, 7, 30))
        status = random.choice(STATUSES)
        cur.execute(
            "INSERT INTO orders (customer_id, order_date, status) VALUES (%s,%s,%s) RETURNING order_id",
            (cust, odate, status),
        )
        order_id = cur.fetchone()[0]

        n_items = random.randint(1, 4)
        chosen_products = random.sample(list(product_ids.keys()), n_items)
        for pid in chosen_products:
            qty = random.randint(1, 3)
            price = product_ids[pid]
            cur.execute(
                "INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES (%s,%s,%s,%s)",
                (order_id, pid, qty, price),
            )

    conn.commit()
    cur.close()
    conn.close()
    print("Database seeded with customers, products, orders, order_items.")


if __name__ == "__main__":
    main()
