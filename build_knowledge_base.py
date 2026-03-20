"""Optional utility to build a knowledge base from explicit source URLs."""

import argparse

from knowledge_base import KnowledgeExtractor
from private_settings import PRIVATE_SETINGS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a knowledge base under knowledge_base/data/<name>. "
            "This is only needed when you want to regenerate KB assets."
        )
    )
    parser.add_argument(
        "--knowledge-base",
        required=True,
        help="Target KB folder name, for example files_Italy.",
    )
    parser.add_argument(
        "--url",
        action="append",
        dest="urls",
        required=True,
        help="Source URL to ingest. Repeat --url for multiple sources.",
    )
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()

    if PRIVATE_SETINGS["LLM_LOCAL"]:
        extractor = KnowledgeExtractor("ollama", "llama3.2", "mxbai-embed-large")
    else:
        extractor = KnowledgeExtractor("openai", "gpt-4", "text-embedding-3-small")

    extractor.run(
        knowledge_base=args.knowledge_base,
        html_links=args.urls,
    )
