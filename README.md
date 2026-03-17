# MDER-DR_RAG

RAG-based project for building a domain knowledge base and answering questions via API or web UI.

## Requirements

- Linux
- Python 3.10+ (recommended)
- `pip`
- (Optional) local LLM runtime (e.g., Ollama) if configured in `private_settings.py`

## Installation (venv + requirements.txt)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## Configuration

Edit `private_settings.py` to set API keys and runtime options (local vs online model usage).

## 1) Create / rebuild knowledge base

Run the knowledge base creator script:

```bash
python build_knowledge_base.py
```

This script mainly calls `KnowledgeExtractor.run(...)` with:
- `knowledge_base="Tomato recipes"`
- one or more URLs in `html_links`
- many `load_cached_*` flags default to `False`

Example with explicit parameters, from `build_knowledge_base.py`:

```python
ke.run(
    knowledge_base="Tomato_recipes",
    html_links=[
        "https://en.wikipedia.org/wiki/Tomato_sauce",
        "https://en.wikipedia.org/wiki/Pasta_al_pomodoro",
    ],
)
```

In this example, artifacts are written under `knowledge_base/data/Tomato_recipes/`

## 2) Run web interface (Streamlit)

Use the Streamlit entrypoint:

```bash
streamlit run streamlit_ui.py
```

## 3) Run question answering directly

Instantiate the `Guru` class from:

- `orchestrator/guru.py`

### Guru class

`Guru` is the main entry point for question answering.

### Parameters needed to instantiate `Guru`

- `provider` (`str`)  
  LLM backend provider (e.g., `"ollama"` or `"openai"`).
- `model` (`str`)  
  Chat/model name (e.g., `"gpt-oss:120b"` or `"gpt-4"`).
- `embedding` (`str`)  
  Embedding model name (e.g., `"mxbai-embed-large"` or `"text-embedding-3-small"`).
- `language` (`str`)  
  Response language (e.g., `"english"`).
- `temperature` (`int | float`)  
  Generation temperature (example in project: `0`).
- `answer_length` (`str`)  
   Output style/length (example: `"compact"`).
- `knowledge_base` (`str`)  
  Knowledge base storage folder (similar concept used in KB creation, e.g., `"Switzerland"`).
  

Example with explicit parameters, from `answer_question.py`:

```python
from orchestrator.guru import Guru

guru = Guru(
    provider="ollama",
    model="gpt-oss:20b",
    embedding="mxbai-embed-large",
    language="english",
    temperature=0,
    answer_length="compact",
    knowledge_base="Italy",
    use_knowledge=True
)

response = guru.user_message("What are the ingredients of Pasta al pomodoro?")
print(response)
```

### Inputs and outputs

**Primary method used in this project:**

- `user_message(question)`

**Input:**

- `question` (`str`): the user request/question in natural language.  
  Example: `"How can I reduce heating energy consumption at home?"`

**Output:**

- `response` (`str`): generated answer text from the RAG pipeline, ready to be shown to the user or returned by an API endpoint.

**Minimal usage flow:**

1. Create a `Guru` instance with your project configuration.
2. Pass a question string to `user_message(...)`.
3. Return or print the resulting answer string.

## 4) Run benchmark

Before running the benchmark, you must provide a dataset file inside the `benchmark/` directory.

- Create a CSV file (e.g., `benchmark_dataset.csv`) in `benchmark/`
- This file should contain:
  - The list of questions to evaluate
  - The corresponding knowledge base

You can run the benchmark with:

```bash
python run_benchmark.py
```

The script will:
- Load the dataset from the benchmark/ folder
- Instantiate the Guru pipeline using the specified settings
- Execute all questions
- Collect and store answers in a separated `.csv` file

<hr>

## Main project files

- `build_knowledge_base.py` — build/update the knowledge base from sources
- `answer_question.py` — CLI-style question answering entrypoint
- `streamlit_ui.py` — web interface
- `run_benchmark.py` — benchmark runner
- `orchestrator/guru.py` — main orchestrator class (`Guru`)
- `knowledge_base/` — extraction and storage logic
- `llm/` — LLM integration layer

## Project tree

```text
MDER-DR_RAG/
├── answer_question.py                # CLI-style question answering entrypoint
├── build_knowledge_base.py           # Build/update the knowledge base from sources
├── run_benchmark.py                  # Benchmark runner
├── streamlit_ui.py                   # Web interface (Streamlit)
├── private_settings.py               # Local/private runtime settings
├── requirements.txt                  # Python dependencies
├── readme.md
├── LICENSE
├── benchmark/
│   ├── __init__.py
│   └── benchmark.py
├── knowledge_base/
│   ├── __init__.py
│   ├── knowledge_extractor.py        # Extracts content and constructs the knowledge graph
│   ├── knowledge_manager.py          # Loads/searches knowledge in the graph at query time
│   ├── data/                         # Stored graph files / serialized KB artifacts
│   └── utils/                        # Helper modules used by KB build/query logic
│       ├── energenius_graph.py
│       ├── graph_helpers.py
│       ├── graph_parameter.py
│       ├── graph_prompt.py
│       └── disambiguator.py
├── llm/
│   ├── __init__.py
│   └── langchain.py                  # LLM + embedding integration layer
└── orchestrator/
    ├── __init__.py
    ├── abstract_orchestrator.py
    ├── guru.py                       # Main API orchestrator class (Guru)
    └── live_orchestrator.py
```

### Notes

- `knowledge_base/knowledge_extractor.py` is used to **create/build** the graph.
- `knowledge_base/knowledge_manager.py` is used to **retrieve/search** knowledge in the graph.
- `knowledge_base/data/` stores graph artifacts.
- `knowledge_base/utils/` contains helper utilities for graph creation and processing.

## Typical workflow

1. Create and activate virtual environment  
2. Install dependencies from `requirements.txt`  
3. Configure `private_settings.py`  
4. Build KB with `python build_knowledge_base.py` (or copy an existing KB to `knowledge_base/data/`)
5. Run either:
   - Web UI: `streamlit run streamlit_ui.py`
   - API integration: instantiate `Guru` in your application/tests
   - Benchmark: `python run_benchmark.py`

## License

See `LICENSE`.

## Citation

```
@misc{campi2026mderdrmultihopquestionanswering,
      title={MDER-DR: Multi-Hop Question Answering with Entity-Centric Summaries}, 
      author={Riccardo Campi and Nicolò Oreste Pinciroli Vago and Mathyas Giudici and Marco Brambilla and Piero Fraternali},
      year={2026},
      eprint={2603.11223},
      archivePrefix={arXiv},
      primaryClass={cs.CL},
      url={https://arxiv.org/abs/2603.11223}, 
}
```
