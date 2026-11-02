from google.genai.errors import APIError

from app.agent import (
    StoreAgent,
    ToolDispatcher,
    create_client,
    load_settings,
)
from app.database import create_database
from app.policy import PolicyRetriever


EXIT_COMMANDS = {
    "sair",
    "exit",
    "quit",
}


def request_order_email():
    print(
        "\nVerificação local: informe o e-mail "
        "associado ao pedido."
    )

    try:
        return input("E-mail do pedido: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()

        return ""


def run_chat(agent):
    print(
        "\nAmy: Olá! Sou a assistente virtual do "
        "Empório da Música."
    )
    print(
        "Posso ajudar com produtos, promoções, "
        "pedidos e políticas da loja."
    )
    print("Digite 'sair' para encerrar.")

    while True:
        try:
            message = input("\nVocê: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\nAmy: Até logo!")
            break

        if not message:
            continue

        if message.casefold() in EXIT_COMMANDS:
            print("\nAmy: Até logo!")
            break

        try:
            answer = agent.ask(message)
        except APIError as error:
            if error.code == 429:
                print(
                    "\nAmy: O serviço atingiu temporariamente "
                    "o limite de uso. Tente novamente mais tarde."
                )
            else:
                print(
                    "\nAmy: Não consegui acessar o serviço "
                    "de IA neste momento."
                )

            continue
        except (RuntimeError, ValueError):
            print(
                "\nAmy: Não consegui concluir essa solicitação. "
                "Tente novamente."
            )
            continue

        print(f"\nAmy: {answer}")


def main():
    api_key, model = load_settings()
    client = create_client(api_key)
    database = create_database()

    try:
        dispatcher = ToolDispatcher(
            database,
            PolicyRetriever(),
            email_provider=request_order_email,
        )

        agent = StoreAgent(
            client,
            model,
            dispatcher,
        )

        run_chat(agent)
    finally:
        client.close()
        database.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())