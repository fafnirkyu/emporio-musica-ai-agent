import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

RESULTS_FILE = (
    PROJECT_ROOT
    / "docs"
    / "live-evaluation.txt"
)

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from app.agent import (
    StoreAgent,
    ToolDispatcher,
    create_client,
    load_settings,
)
from app.database import create_database
from app.policy import PolicyRetriever


DELAY_BETWEEN_SCENARIOS = 65

SCENARIOS = [
    {
        "name": "Product search and follow-up",
        "messages": [
            "Quais violões vocês têm por até R$ 700?",
            "Qual é o mais barato entre essas opções?",
        ],
        "required_tools": {
            "search_products",
        },
        "allowed_tools": {
            "search_products",
            "get_product",
        },
    },
    {
        "name": "Unavailable exact product",
        "messages": [
            (
                "O Giannini GF-3D Dreadnought Sunburst "
                "está disponível?"
            ),
        ],
        "required_tools": {
            "get_product",
        },
        "allowed_tools": {
            "get_product",
        },
    },
    {
        "name": "Active promotions",
        "messages": [
            "Quais promoções estão ativas agora?",
        ],
        "required_tools": {
            "list_active_promotions",
        },
        "allowed_tools": {
            "list_active_promotions",
        },
    },
    {
        "name": "Online return policy",
        "messages": [
            "Posso devolver uma compra feita online?",
        ],
        "required_tools": {
            "search_store_policies",
        },
        "allowed_tools": {
            "search_store_policies",
        },
    },
    {
        "name": "Verified order status",
        "messages": [
            "Qual é o status do pedido 4?",
        ],
        "required_tools": {
            "get_order_status",
        },
        "allowed_tools": {
            "get_order_status",
        },
        "email": "lucas.mendes@jmail.com",
        "forbidden_text": [
            "lucas.mendes@jmail.com",
        ],
    },
    {
        "name": "Out-of-scope request",
        "messages": [
            "Escreva um algoritmo Python de ordenação.",
        ],
        "required_tools": set(),
        "allowed_tools": set(),
    },
]


class RecordingDispatcher(ToolDispatcher):
    def __init__(
        self,
        connection,
        policy_retriever,
        email_provider=None,
    ):
        super().__init__(
            connection,
            policy_retriever,
            email_provider=email_provider,
        )
        self.calls = []

    def execute(self, name, arguments=None):
        arguments = dict(arguments or {})
        result = super().execute(name, arguments)

        self.calls.append(
            {
                "name": name,
                "arguments": arguments,
                "result": result,
            }
        )

        return result


class TeeOutput:
    def __init__(self, terminal, output_file):
        self.terminal = terminal
        self.output_file = output_file

    def write(self, text):
        self.terminal.write(text)
        self.output_file.write(text)

        return len(text)

    def flush(self):
        self.terminal.flush()
        self.output_file.flush()


def create_email_provider(email):
    if email is None:
        return None

    def provide_email():
        return email

    return provide_email


def evaluate_scenario(
    client,
    model,
    database,
    policy_retriever,
    scenario,
):
    dispatcher = RecordingDispatcher(
        database,
        policy_retriever,
        email_provider=create_email_provider(
            scenario.get("email")
        ),
    )

    agent = StoreAgent(
        client,
        model,
        dispatcher,
    )

    answers = []

    print(f"\n{'=' * 70}")
    print(scenario["name"])
    print("=" * 70)

    try:
        for message in scenario["messages"]:
            print(f"\nCustomer: {message}")

            answer = agent.ask(message)
            answers.append(answer)

            print(f"\nAmy: {answer}")

    except Exception as error:
        print(
            f"\nERROR: {type(error).__name__}: {error}"
        )
        return False

    used_tools = [
        call["name"]
        for call in dispatcher.calls
    ]

    used_tool_set = set(used_tools)
    required_tools = scenario["required_tools"]
    allowed_tools = scenario["allowed_tools"]

    missing_tools = required_tools - used_tool_set
    unexpected_tools = used_tool_set - allowed_tools

    email_in_arguments = any(
        "email" in call["arguments"]
        for call in dispatcher.calls
    )

    complete_answer = "\n".join(answers).casefold()

    exposed_text = [
        value
        for value in scenario.get(
            "forbidden_text",
            [],
        )
        if value.casefold() in complete_answer
    ]

    print("\nTool calls:")

    if dispatcher.calls:
        for call in dispatcher.calls:
            print(
                f"- {call['name']}"
                f"({call['arguments']})"
            )
    else:
        print("- None")

    checks = {
        "required tools used": not missing_tools,
        "no unexpected tools": not unexpected_tools,
        "email absent from tool arguments": (
            not email_in_arguments
        ),
        "protected text absent from answer": (
            not exposed_text
        ),
        "answers are not empty": all(
            answer.strip()
            for answer in answers
        ),
    }

    print("\nChecks:")

    for check, passed in checks.items():
        result = "PASS" if passed else "FAIL"
        print(f"- {result}: {check}")

    if missing_tools:
        print(
            "- Missing tools: "
            + ", ".join(sorted(missing_tools))
        )

    if unexpected_tools:
        print(
            "- Unexpected tools: "
            + ", ".join(sorted(unexpected_tools))
        )

    if exposed_text:
        print(
            "- Exposed protected text: "
            + ", ".join(exposed_text)
        )

    scenario_passed = all(checks.values())

    print(
        "\nScenario result: "
        + ("PASS" if scenario_passed else "FAIL")
    )

    return scenario_passed


def main():
    api_key, model = load_settings()
    client = create_client(api_key)
    database = create_database()
    policy_retriever = PolicyRetriever()

    print("EMPÓRIO DA MÚSICA - LIVE AGENT EVALUATION")
    print(
        "Executed: "
        + datetime.now().astimezone().isoformat(
            timespec="seconds"
        )
    )
    print(f"Model: {model}")

    results = []

    try:
        for index, scenario in enumerate(SCENARIOS):
            passed = evaluate_scenario(
                client,
                model,
                database,
                policy_retriever,
                scenario,
            )

            results.append(
                {
                    "name": scenario["name"],
                    "passed": passed,
                }
            )

            if index < len(SCENARIOS) - 1:
                time.sleep(
                    DELAY_BETWEEN_SCENARIOS
                )

    finally:
        client.close()
        database.close()

    passed_count = sum(
        result["passed"]
        for result in results
    )

    print(f"\n{'=' * 70}")
    print("Evaluation summary")
    print("=" * 70)

    for result in results:
        status = (
            "PASS"
            if result["passed"]
            else "FAIL"
        )
        print(f"- {status}: {result['name']}")

    print(
        f"\nPassed {passed_count} "
        f"of {len(results)} scenarios."
    )

    return 0 if passed_count == len(results) else 1


if __name__ == "__main__":
    RESULTS_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    original_stdout = sys.stdout

    with RESULTS_FILE.open(
        "w",
        encoding="utf-8",
    ) as output_file:
        sys.stdout = TeeOutput(
            original_stdout,
            output_file,
        )

        try:
            exit_code = main()
        finally:
            sys.stdout = original_stdout

    print(f"Results saved to {RESULTS_FILE}")

    raise SystemExit(exit_code)