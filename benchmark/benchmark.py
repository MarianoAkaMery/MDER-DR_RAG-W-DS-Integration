"""Module to benchmark the Guru"""

import tqdm
import pandas as pd
import time

from orchestrator import Guru


class Benchmark:
    """Benchmark to test Q&A on a dataset"""

    def __init__(self):
        pass

    @staticmethod
    def run(
        guru: Guru, dataset: pd.DataFrame, target_column: str, languages: list[str], region_column: str
    ) -> pd.DataFrame:
        """Run the benchmark on the dataset

        Args:
            guru (Guru): _Guru instance_
            dataset (pd.DataFrame): _dataset to benchmark_
            target_column(str): _target column for the questions (language will be automatically appended)_
            languages (list[str]): _list of languages to benchmark_

        Returns:
            pd.DataFrame: _dataset with answers_
        """
        with tqdm.tqdm(total=dataset.shape[0]) as pbar:
            for index, row in dataset.iterrows():
                for l in languages:
                    # Getting the question
                    question = row[f"{target_column}{l}"]
                    # Setting the language
                    guru.set_language(l)
                    guru.set_knowledge_base(row[region_column])
                    guru.set_temperature(0.0)
                    # Creating the answer
                    print(question, l, row[region_column])
                    answer = guru.user_message(question).replace("\n", " ").replace("  ", " ")
                    # Putting the answer in the dataset
                    dataset.at[index, f"ANSWER_{l}"] = answer
                    print(answer)
                    time.sleep(0.1)  # 100 milliseconds = 0.1 seconds
                pbar.update(1)

        return dataset
