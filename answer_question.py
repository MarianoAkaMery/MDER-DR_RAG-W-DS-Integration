"""CLI helper to test the Guru orchestrator with a single question."""

from __future__ import annotations

import argparse

from orchestrator import Guru
from private_settings import PRIVATE_SETINGS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ask one question to the Guru orchestrator from the command line."
    )
    parser.add_argument(
        "question",
        nargs="?",
        default="What incentives are available for home energy efficiency in Italy?",
        help="Question to send to Guru.",
    )
    parser.add_argument(
        "--language",
        default="English",
        choices=["English", "Italiano"],
        help="Response language.",
    )
    parser.add_argument(
        "--knowledge-base",
        default="Italy",
        choices=["Italy", "Switzerland", "Europe", "Generic"],
        help="Knowledge base to use.",
    )
    parser.add_argument(
        "--answer-length",
        default="Compact",
        choices=["Compact", "Extensive", "Markdown"],
        help="Requested answer format/length.",
    )
    parser.add_argument(
        "--temperature",
        default=0.0,
        type=float,
        help="Model temperature.",
    )
    parser.add_argument(
        "--no-knowledge",
        action="store_true",
        help="Disable the knowledge base and use only the LLM fallback.",
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        help="Use streaming output like the UI.",
    )
    return parser


def build_guru(args: argparse.Namespace) -> Guru:
    if PRIVATE_SETINGS["LLM_LOCAL"]:
        provider = "ollama"
        model = "llama3.2"
        embedding = "mxbai-embed-large"
    else:
        provider = "openai"
        model = "gpt-4"
        embedding = "text-embedding-3-small"

    return Guru(
        provider=provider,
        model=model,
        embedding=embedding,
        language=args.language,
        temperature=args.temperature,
        answer_length=args.answer_length,
        knowledge_base=args.knowledge_base,
        use_knowledge=not args.no_knowledge,
    )


if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()

    guru = build_guru(args)

    print("=== Guru Test ===")
    print(f"Language: {args.language}")
    print(f"Knowledge Base: {args.knowledge_base}")
    print(f"Use Knowledge Base: {not args.no_knowledge}")
    print(f"Question: {args.question}")
    print()

    if args.stream:
        for chunk in guru.user_message_stream(args.question):
            print(chunk, end="", flush=True)
        print()
    else:
        response = guru.user_message(args.question)
        print(response)
