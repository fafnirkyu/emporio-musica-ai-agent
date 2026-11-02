from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.agent import (
    MAX_TOOL_ROUNDS,
    PRODUCT_CATEGORIES,
    TOOL_DECLARATIONS,
    StoreAgent,
    ToolDispatcher,
)
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


def model_response(text=None, function_calls=None):
    return SimpleNamespace(
        text=text,
        function_calls=function_calls or [],
    )


def create_fake_agent(responses, dispatcher):
    chat = Mock()
    chat.send_message.side_effect = responses

    client = Mock()
    client.chats.create.return_value = chat

    agent = StoreAgent(
        client=client,
        model="test-model",
        dispatcher=dispatcher,
    )

    return agent, chat



def test_returns_model_answer_without_tool_call(dispatcher):
    agent, chat = create_fake_agent(
        [
            model_response(
                text="Olá! Como posso ajudar?"
            )
        ],
        dispatcher,
    )

    answer = agent.ask("Olá")

    assert answer == "Olá! Como posso ajudar?"
    assert chat.send_message.call_count == 1
    assert chat.send_message.call_args.args[0] == "Olá"


def test_executes_model_tool_call(dispatcher):
    function_call = SimpleNamespace(
        name="search_products",
        args={
            "query": "violão",
            "limit": 2,
        },
    )

    agent, chat = create_fake_agent(
        [
            model_response(
                function_calls=[function_call]
            ),
            model_response(
                text="Encontrei dois violões."
            ),
        ],
        dispatcher,
    )

    answer = agent.ask("Quero ver dois violões")

    assert answer == "Encontrei dois violões."
    assert chat.send_message.call_count == 2

    tool_parts = chat.send_message.call_args_list[
        1
    ].args[0]

    function_response = tool_parts[
        0
    ].function_response

    assert function_response.name == "search_products"
    assert function_response.response[
        "result"
    ]["count"] == 2


def test_rejects_empty_user_message(dispatcher):
    agent, chat = create_fake_agent(
        [],
        dispatcher,
    )

    with pytest.raises(
        ValueError,
        match="Message cannot be empty",
    ):
        agent.ask("   ")

    chat.send_message.assert_not_called()


def test_rejects_empty_model_response(dispatcher):
    agent, _ = create_fake_agent(
        [
            model_response(text="   ")
        ],
        dispatcher,
    )

    with pytest.raises(
        RuntimeError,
        match="model returned an empty response",
    ):
        agent.ask("Olá")


def test_stops_repeated_tool_calls(dispatcher):
    function_call = SimpleNamespace(
        name="search_products",
        args={
            "query": "violão",
        },
    )

    responses = [
        model_response(
            function_calls=[function_call]
        )
        for _ in range(MAX_TOOL_ROUNDS + 1)
    ]

    agent, chat = create_fake_agent(
        responses,
        dispatcher,
    )

    with pytest.raises(
        RuntimeError,
        match="exceeded the tool call limit",
    ):
        agent.ask("Procure um violão")

    assert chat.send_message.call_count == (
        MAX_TOOL_ROUNDS + 1
    )


def test_keeps_gemini_client_alive(dispatcher):
    client = Mock()
    client.chats.create.return_value = Mock()

    agent = StoreAgent(
        client=client,
        model="test-model",
        dispatcher=dispatcher,
    )

    assert agent.client is client


def test_declared_categories_match_database(database):
    database_categories = [
        row["name"]
        for row in database.execute(
            "SELECT name FROM categories ORDER BY name"
        ).fetchall()
    ]

    search_declaration = next(
        declaration
        for declaration in TOOL_DECLARATIONS
        if declaration.name == "search_products"
    )

    category_schema = (
        search_declaration.parameters_json_schema[
            "properties"
        ]["category"]
    )

    assert PRODUCT_CATEGORIES == database_categories
    assert category_schema["enum"] == PRODUCT_CATEGORIES