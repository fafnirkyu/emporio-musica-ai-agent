import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

from app import store
from app.database import money_to_cents


DEFAULT_MODEL = "gemini-2.5-flash"

SYSTEM_INSTRUCTION = """
Você é Amy, a assistente virtual do Empório da Música.

Responda em português brasileiro de forma amigável, clara e objetiva. Você é
uma assistente de IA e não deve fingir ser uma atendente humana.

Ajude apenas com produtos, preços, estoque, promoções, pedidos e políticas da
loja. Para informações fora desse escopo, explique educadamente que só pode
ajudar com assuntos relacionados ao Empório da Música.

Use as ferramentas disponíveis sempre que a resposta depender de dados da
loja. Preços, estoque, promoções e pedidos devem vir das ferramentas de dados
estruturados. Trocas, devoluções, pagamentos, entregas e outras regras da loja
devem vir da ferramenta de políticas.

Para consultar um pedido, peça apenas o número do pedido na conversa. O
aplicativo solicitará o e-mail separadamente para verificação. Não peça o
e-mail diretamente pelo chat.

Nunca invente produtos, preços, disponibilidade, informações de pedidos ou
regras. Se uma busca não encontrar informações suficientes, diga isso
claramente. Não mencione ferramentas internas, SQL, arquivos ou detalhes da
implementação ao cliente.
""".strip()


def load_settings():
    load_dotenv()

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL).strip()

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is missing from the environment."
        )

    if not model:
        model = DEFAULT_MODEL

    return api_key, model


def create_client(api_key):
    return genai.Client(api_key=api_key)


TOOL_DECLARATIONS = [
    types.FunctionDeclaration(
        name="search_products",
        description=(
            "Searches the store catalog using a product description, "
            "category, maximum price in Brazilian reais, or a combination "
            "of these filters."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Product name, type, feature, or description."
                    ),
                },
                "category": {
                    "type": "string",
                    "description": "Product category requested by the user.",
                },
                "maximum_price_brl": {
                    "type": "number",
                    "description": (
                        "Maximum price in Brazilian reais, such as 500.00."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": (
                        "Maximum number of products to return, from 1 to 10."
                    ),
                },
            },
        },
    ),
    types.FunctionDeclaration(
        name="get_product",
        description=(
            "Retrieves the exact details, price, stock status and "
            "specifications of a named product."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Exact or approximate product name.",
                },
            },
            "required": ["name"],
        },
    ),
    types.FunctionDeclaration(
        name="list_active_promotions",
        description=(
            "Lists current promotions for products that are available "
            "for purchase."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": (
                        "Maximum number of promotions to return, from 1 to 10."
                    ),
                },
            },
        },
    ),
    types.FunctionDeclaration(
        name="get_order_status",
        description=(
            "Retrieves an order after locally verifying the customer email. "
            "Use it when the customer asks about an existing order."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "integer",
                    "description": "Numeric order identifier.",
                },
            },
            "required": ["order_id"],
        },
    ),
    types.FunctionDeclaration(
        name="search_store_policies",
        description=(
            "Searches official store policies about payments, shipping, "
            "returns, exchanges, warranties and store procedures."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "The customer's complete question about store rules."
                    ),
                },
            },
            "required": ["query"],
        },
    ),
]

STORE_TOOLS = [
    types.Tool(function_declarations=TOOL_DECLARATIONS)
]


class ToolDispatcher:
    def __init__(
        self,
        connection,
        policy_retriever,
        email_provider=None,
    ):
        self.connection = connection
        self.policy_retriever = policy_retriever
        self.email_provider = email_provider

        self.handlers = {
            "search_products": self.search_products,
            "get_product": self.get_product,
            "list_active_promotions": self.list_active_promotions,
            "get_order_status": self.get_order_status,
            "search_store_policies": self.search_store_policies,
        }

    def execute(self, name, arguments=None):
        handler = self.handlers.get(name)

        if handler is None:
            return {
                "error": "This tool is not available."
            }

        try:
            return handler(**dict(arguments or {}))
        except (TypeError, ValueError) as error:
            return {
                "error": str(error)
            }

    def search_products(
        self,
        query=None,
        category=None,
        maximum_price_brl=None,
        limit=5,
    ):
        maximum_price_cents = None

        if maximum_price_brl is not None:
            maximum_price_cents = money_to_cents(
                maximum_price_brl
            )

        return store.search_products(
            self.connection,
            query=query,
            category=category,
            maximum_price_cents=maximum_price_cents,
            limit=limit,
        )

    def get_product(self, name):
        return store.get_product(
            self.connection,
            name=name,
        )

    def list_active_promotions(self, limit=5):
        return store.list_active_promotions(
            self.connection,
            limit=limit,
        )

    def get_order_status(self, order_id):
        if self.email_provider is None:
            return {
                "verified": False,
                "message": (
                    "Email verification is not available."
                ),
            }

        email = (self.email_provider() or "").strip()

        if not email:
            return {
                "verified": False,
                "message": "Email verification was cancelled.",
            }

        return store.get_order_status(
            self.connection,
            order_id=order_id,
            email=email,
        )

    def search_store_policies(self, query):
        return self.policy_retriever.search(query)