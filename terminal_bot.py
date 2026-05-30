import os
import sys

from dotenv import load_dotenv

from assistant_service import process_question_sync

load_dotenv()

EXIT_COMMANDS = {"exit", "quit", "q"}
SEPARATOR = "---"
GOODBYE = (
    "Thank you for using Shopee Seller AI Assistant.\n"
    "Goodbye!"
)


def _print_welcome() -> None:
    print("Shopee Seller AI Assistant")
    print()
    print("How can I help you today?")
    print()


def _print_turn_prompt() -> None:
    print("How can I help you today?")
    print()


def main() -> None:
    _print_welcome()

    if not os.getenv("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY is not set.")
        print("Copy .env.example to .env and add your Anthropic API key.")
        sys.exit(1)

    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            print(GOODBYE)
            break

        if not question:
            continue

        if question.lower() in EXIT_COMMANDS:
            print(GOODBYE)
            break

        print("\nResearching Seller Education...\n")

        try:
            result = process_question_sync(question)
            print()
            print(result["formatted"])
        except Exception as exc:
            print(f"\nError: {exc}")

        print()
        print(SEPARATOR)
        print()
        _print_turn_prompt()


if __name__ == "__main__":
    main()
