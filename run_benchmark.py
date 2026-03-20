"""Module to benchmark a specific knowledge base."""

import pandas as pd

from benchmark import Benchmark
from orchestrator import Guru
from private_settings import PRIVATE_SETINGS


if __name__ == "__main__":
    # Load the dataset
    dataset = pd.read_csv("benchmark/benchmark_dataset.csv")

    # Create the Guru instance
    if PRIVATE_SETINGS["LLM_LOCAL"]:
        guru = Guru("ollama", "gpt-oss:20b", "mxbai-embed-large", "English", 0, "Compact", "Italy")
    else:
        guru = Guru("openai", "gpt-4", "text-embedding-3-small", "English", 0, "Compact", "Italy")

    # Define the languages to benchmark
    languages = ["Italiano", "English"]

    # Run the benchmark
    result = Benchmark.run(guru, dataset, "Question - ", languages, "Region")

    # Save the result to a CSV file
    result.to_csv("benchmark/benchmark_results.csv", columns=["Question - Italiano", "Answer - Italiano", "ANSWER_Italiano", "Question - English", "Answer - English", "ANSWER_English", "Source", "Region"], index=False)

