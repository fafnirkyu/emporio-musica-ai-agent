import pytest

from app.database import create_database
from app.store import (
    get_order_status,
    get_product,
    list_active_promotions,
    search_products,
)


@pytest.fixture
def database():
    connection = create_database()

    yield connection

    connection.close()


def test_filters_products_by_category_and_budget(database):
    result = search_products(
        database,
        category="Violões",
        maximum_price_cents=100000,
        limit=10,
    )

    assert result["count"] == 10
    assert all(
        product["category"] == "Violões"
        for product in result["products"]
    )
    assert all(
        product["current_price_cents"] <= 100000
        for product in result["products"]
    )
    assert all(
        product["product_id"] != 128
        for product in result["products"]
    )


def test_places_available_products_before_unavailable_products(database):
    result = search_products(
        database,
        query="Giannini",
        limit=10,
    )

    availability = [
        product["availability"]
        for product in result["products"]
    ]

    assert availability[:-1] == ["available"] * 4
    assert availability[-1] == "out_of_stock"
    assert result["products"][-1]["display_name"].startswith(
        "[SEM ESTOQUE]"
    )


def test_uses_promotional_price_for_budget_filter(database):
    result = search_products(
        database,
        query="Ohana",
        maximum_price_cents=45000,
    )

    product = result["products"][0]

    assert product["product_id"] == 121
    assert product["original_price_cents"] == 54900
    assert product["current_price_cents"] == 43920
    assert product["promotion"]["discount_percent"] == 20


def test_lists_only_available_active_promotions(database):
    result = list_active_promotions(
        database,
        limit=10,
    )

    assert result["count"] == 4
    assert all(
        product["available"]
        for product in result["products"]
    )
    assert all(
        product["promotion"] is not None
        for product in result["products"]
    )
    assert all(
        product["current_price_cents"]
        < product["original_price_cents"]
        for product in result["products"]
    )


def test_reports_exact_unavailable_product(database):
    result = get_product(
        database,
        "Giannini GF-3D Dreadnought Sunburst",
    )

    assert result["found"] is True
    assert result["exact_match"] is True
    assert result["product"]["available"] is False
    assert result["product"]["availability"] == "out_of_stock"
    assert result["product"]["display_name"].startswith(
        "[SEM ESTOQUE]"
    )


def test_returns_order_for_matching_email(database):
    result = get_order_status(
        database,
        order_id=4,
        email="LUCAS.MENDES@JMAIL.COM",
    )

    assert result["verified"] is True
    assert result["order"]["order_id"] == 4
    assert result["order"]["status"] == "delivered"
    assert result["order"]["total_cents"] == 79990
    assert result["order"]["total_brl"] == "R$ 799,90"
    assert result["order"]["items"]


def test_hides_whether_an_order_exists(database):
    wrong_email = get_order_status(
        database,
        order_id=4,
        email="wrong@example.com",
    )
    missing_order = get_order_status(
        database,
        order_id=999,
        email="wrong@example.com",
    )

    assert wrong_email == missing_order
    assert wrong_email["verified"] is False
    assert "order" not in wrong_email


def test_limits_product_results_to_ten(database):
    result = search_products(
        database,
        limit=100,
    )

    assert result["count"] == 10