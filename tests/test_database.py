import sqlite3

import pytest

from app.database import create_database


EXPECTED_COUNTS = {
    "categories": 9,
    "products": 65,
    "customers": 50,
    "orders": 20,
    "order_items": 22,
    "promotions": 25,
}


@pytest.fixture
def database():
    connection = create_database()

    yield connection

    connection.close()


def test_loads_expected_rows(database):
    for table, expected_count in EXPECTED_COUNTS.items():
        result = database.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()

        assert result[0] == expected_count


def test_enables_foreign_keys(database):
    result = database.execute("PRAGMA foreign_keys").fetchone()

    assert result[0] == 1


def test_converts_money_to_cents(database):
    product = database.execute(
        """
        SELECT price_cents
        FROM products
        WHERE product_id = 81
        """
    ).fetchone()

    order = database.execute(
        """
        SELECT total_cents
        FROM orders
        WHERE order_id = 4
        """
    ).fetchone()

    assert product["price_cents"] == 59990
    assert order["total_cents"] == 79990


def test_converts_empty_values_to_null(database):
    order = database.execute(
        """
        SELECT notes
        FROM orders
        WHERE order_id = 1
        """
    ).fetchone()

    assert order["notes"] is None


def test_rejects_missing_customer_reference(database):
    with pytest.raises(sqlite3.IntegrityError):
        database.execute(
            """
            INSERT INTO orders (
                order_id,
                customer_id,
                order_date,
                status,
                total_cents,
                payment_method
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                999,
                999,
                "2026-10-31",
                "pending",
                10000,
                "pix",
            ),
        )


def test_databases_are_independent():
    first_database = create_database()
    second_database = create_database()

    try:
        first_database.execute(
            """
            UPDATE products
            SET name = ?
            WHERE product_id = ?
            """,
            ("Changed only in the first database", 81),
        )

        first_name = first_database.execute(
            """
            SELECT name
            FROM products
            WHERE product_id = 81
            """
        ).fetchone()["name"]

        second_name = second_database.execute(
            """
            SELECT name
            FROM products
            WHERE product_id = 81
            """
        ).fetchone()["name"]

        assert first_name == "Changed only in the first database"
        assert second_name == "Yamaha C40 Nylon Natural"
    finally:
        first_database.close()
        second_database.close()