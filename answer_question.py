"""Module to answer a question using the Guru orchestrator."""

from orchestrator import Guru
from private_settings import PRIVATE_SETINGS


if __name__ == "__main__":

    # Create the Guru instance
    if PRIVATE_SETINGS["LLM_LOCAL"]:
        guru = Guru("ollama", "llama3.2", "mxbai-embed-large", "english", 0, "compact", "Italy")
    else:
        guru = Guru("openai", "gpt-4", "text-embedding-3-small", "english", 0, "compact", "Italy")

    # Run the guru
    response = guru.user_message("What are the ingredients of Pasta al pomodoro?")
    print(response)
