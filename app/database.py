import json
import sqlite3
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

FILES = {
    "categories": "desafio_tecnico_ai_eng - categories.csv",
    "products": "desafio_tecnico_ai_eng - products.csv",
    "customers": "desafio_tecnico_ai_eng - customers.csv",
    "orders": "desafio_tecnico_ai_eng - orders.csv",
    "order_items": "desafio_tecnico_ai_eng - order_items.csv",
    "promotions": "desafio_tecnico_ai_eng - promotions.csv",
}

TABLE_COLUMNS = {
    "categories": ["category_id", "name", "description"],
    "products": [
        "product_id",
        "price_cents",
        "name",
        "category_id",
        "description",
        "stock_quantity",
        "status",
        "specs_json",
        "created_at",
    ],
    "customers": ["customer_id", "name", "phone", "email", "city"],
    "orders": [
        "order_id",
        "customer_id",
        "order_date",
        "status",
        "total_cents",
        "payment_method",
        "tracking_code",
        "estimated_delivery",
        "notes",
    ],
    "order_items": ["order_id", "product_id", "quantity"],
    "promotions": [
        "promotion_id",
        "product_id",
        "discount_percent",
        "description",
        "is_active",
    ],
}

LOAD_ORDER = [
    "categories",
    "products",
    "customers",
    "orders",
    "order_items",
    "promotions",
]

SCHEMA = """
CREATE TABLE categories (
    category_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL
);

CREATE TABLE products (
    product_id INTEGER PRIMARY KEY,
    price_cents INTEGER NOT NULL CHECK (price_cents >= 0),
    name TEXT NOT NULL,
    category_id INTEGER NOT NULL REFERENCES categories(category_id),
    description TEXT NOT NULL,
    stock_quantity INTEGER NOT NULL CHECK (stock_quantity >= 0),
    status TEXT NOT NULL,
    specs_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    email TEXT NOT NULL,
    city TEXT NOT NULL
);

CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    order_date TEXT NOT NULL,
    status TEXT NOT NULL,
    total_cents INTEGER NOT NULL CHECK (total_cents >= 0),
    payment_method TEXT NOT NULL,
    tracking_code TEXT,
    estimated_delivery TEXT,
    notes TEXT
);

CREATE TABLE order_items (
    order_id INTEGER NOT NULL REFERENCES orders(order_id),
    product_id INTEGER NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (order_id, product_id)
);

CREATE TABLE promotions (
    promotion_id INTEGER PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(product_id),
    discount_percent INTEGER NOT NULL
        CHECK (discount_percent BETWEEN 0 AND 100),
    description TEXT NOT NULL,
    is_active INTEGER NOT NULL CHECK (is_active IN (0, 1))
);
"""

# Create and populate a new in-memory database.
def create_database(data_dir=DATA_DIR):

    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    try:
        connection.executescript(SCHEMA)
        frames = load_data(Path(data_dir))

        with connection:
            for table in LOAD_ORDER:
                insert_frame(connection, table, frames[table])
    except Exception:
        connection.close()
        raise

    return connection


# Read the CSV files and prepare their column types.
def load_data(data_dir):

    frames = {
        table: pd.read_csv(
            data_dir / filename,
            dtype=str,
            keep_default_na=False,
        )
        for table, filename in FILES.items()
    }

    categories = frames["categories"]
    convert_to_int(categories, ["category_id"])

    products = frames["products"]
    convert_to_int(
        products,
        ["product_id", "category_id", "stock_quantity"],
    )
    products["price_brl"] = products["price_brl"].map(money_to_cents)
    products["created_at"] = products["created_at"].map(validate_date)
    products["specs"] = products["specs"].map(validate_json)
    products.rename(
        columns={
            "price_brl": "price_cents",
            "specs": "specs_json",
        },
        inplace=True,
    )

    customers = frames["customers"]
    convert_to_int(customers, ["customer_id"])

    orders = frames["orders"]
    convert_to_int(orders, ["order_id", "customer_id"])
    orders["total_brl"] = orders["total_brl"].map(money_to_cents)
    orders["order_date"] = orders["order_date"].map(validate_date)
    orders["estimated_delivery"] = orders["estimated_delivery"].map(
        optional_date
    )
    orders.rename(
        columns={"total_brl": "total_cents"},
        inplace=True,
    )

    order_items = frames["order_items"]
    convert_to_int(
        order_items,
        ["order_id", "product_id", "quantity"],
    )

    promotions = frames["promotions"]
    convert_to_int(
        promotions,
        [
            "promotion_id",
            "product_id",
            "discount_percent",
            "is_active",
        ],
    )

    for frame in frames.values():
        frame.replace({"": None}, inplace=True)

    return frames


# Insert one DataFrame into its matching SQLite table.
def insert_frame(connection, table, frame):

    columns = TABLE_COLUMNS[table]
    column_names = ", ".join(columns)
    placeholders = ", ".join("?" for _ in columns)

    query = (
        f"INSERT INTO {table} ({column_names}) "
        f"VALUES ({placeholders})"
    )

    rows = frame[columns].itertuples(index=False, name=None)
    connection.executemany(query, rows)


def convert_to_int(frame, columns):
    for column in columns:
        frame[column] = pd.to_numeric(
            frame[column],
            errors="raise",
        ).astype(int)


def money_to_cents(value):
    amount = Decimal(value)
    cents = (amount * 100).quantize(
        Decimal("1"),
        rounding=ROUND_HALF_UP,
    )

    if cents < 0:
        raise ValueError("Money values cannot be negative")

    return int(cents)


def validate_date(value):
    return date.fromisoformat(value).isoformat()


def optional_date(value):
    if not value:
        return None

    return validate_date(value)


def validate_json(value):
    parsed = json.loads(value)

    return json.dumps(
        parsed,
        ensure_ascii=False,
        separators=(",", ":"),
    )