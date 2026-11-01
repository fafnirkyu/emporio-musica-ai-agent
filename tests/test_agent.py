import pytest

from app.agent import TOOL_DECLARATIONS, ToolDispatcher
from app.database import create_database
from app.policy import PolicyRetriever


@pytest.fixture
def database():
    connection = create_database()

    yield connection

    connection.close()


@pytest.fixture(scope="module")
def policy_retriever():
    return PolicyRetriever()


@pytest.fixture
def dispatcher(database, policy_retriever):
    return ToolDispatcher(
        database,
        policy_retriever,
    )


def test_declared_tools_match_dispatcher(dispatcher):
    declared_tools = {
        declaration.name
        for declaration in TOOL_DECLARATIONS
    }

    assert declared_tools == set(dispatcher.handlers)


def test_converts_maximum_price_to_cents(dispatcher):
    result = dispatcher.execute(
        "search_products",
        {
            "category": "Violões",
            "maximum_price_brl": 700,
            "limit": 10,
        },
    )

    assert result["products"]
    assert all(
        product["current_price_cents"] <= 70000
        for product in result["products"]
    )


def test_dispatches_exact_product_search(dispatcher):
    result = dispatcher.execute(
        "get_product",
        {
            "name": "Yamaha C40 Nylon Natural",
        },
    )

    assert result["found"] is True
    assert result["product"]["product_id"] == 81


def test_dispatches_promotion_search(dispatcher):
    result = dispatcher.execute(
        "list_active_promotions",
        {
            "limit": 10,
        },
    )

    assert result["count"] == 4
    assert all(
        product["available"]
        for product in result["products"]
    )


def test_dispatches_policy_search(dispatcher):
    result = dispatcher.execute(
        "search_store_policies",
        {
            "query": "Posso devolver uma compra online?",
        },
    )

    assert result["found"] is True
    assert result["matched_page"] == 4


def test_verifies_order_with_local_email(
    database,
    policy_retriever,
):
    dispatcher = ToolDispatcher(
        database,
        policy_retriever,
        email_provider=lambda: "lucas.mendes@jmail.com",
    )

    result = dispatcher.execute(
        "get_order_status",
        {
            "order_id": 4,
        },
    )

    assert result["verified"] is True
    assert result["order"]["order_id"] == 4


def test_hides_order_without_email_provider(dispatcher):
    result = dispatcher.execute(
        "get_order_status",
        {
            "order_id": 4,
        },
    )

    assert result["verified"] is False
    assert "order" not in result


def test_rejects_unknown_tool(dispatcher):
    result = dispatcher.execute("delete_database")

    assert result == {
        "error": "This tool is not available."
    }


def test_returns_controlled_argument_error(dispatcher):
    result = dispatcher.execute(
        "search_products",
        {
            "maximum_price_brl": "not a price",
        },
    )

    assert result == {
        "error": "Money values must be valid numbers"
    }