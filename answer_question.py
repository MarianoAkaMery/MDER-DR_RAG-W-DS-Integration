"""Module to answer a question using the Guru orchestrator."""

from orchestrator import Guru
from private_settings import PRIVATE_SETINGS


if __name__ == "__main__":

    # Create the Guru instance
    if PRIVATE_SETINGS["LLM_LOCAL"]:
        guru = Guru("ollama", "llama3.2", "mxbai-embed-large", "English", 0, "Compact", "Italy")
    else:
        guru = Guru("openai", "gpt-4", "text-embedding-3-small", "English", 0, "Compact", "Italy")

    # Run the guru
    response = guru.user_message("What incentives are available for home energy efficiency in Italy?")
    print(response)
