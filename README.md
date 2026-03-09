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

## Run modes

### 1) Web interface (Streamlit)

Use the Streamlit entrypoint:

```bash
streamlit run streamlit_ui.py
```

### 2) API mode

Instantiate the `Guru` class from:

- `orchestrator/guru.py`

Example (minimal), from `answer_question.py`:

```python
from orchestrator.guru import Guru

guru = Guru(...)
response = guru.user_message("Your question here")
print(response)
```

#### Guru class

`Guru` is the main API entry point for question answering.

#### Parameters needed to instantiate `Guru`

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
  

Example with explicit parameters:

```python
from orchestrator.guru import Guru

guru = Guru(
    provider="ollama",
    model="gpt-oss:120b",
    embedding="mxbai-embed-large",
    language="english",
    temperature=0,
    answer_length="compact",
    knowledge_base="Switzerland",
    use_knowledge: bool = True
)
```

#### Inputs and outputs

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

### 3) Create / rebuild knowledge base

Run the knowledge base creator script:

```bash
python build_knowledge_base.py
```

### 4) Run benchmark

You can run the benchmark with:

```bash
python run_benchmark.py
```

## Main project files

- `build_knowledge_base.py` — build/update the knowledge base from sources
- `answer_question.py` — CLI-style question answering entrypoint
- `streamlit_ui.py` — web interface
- `run_benchmark.py` — benchmark runner
- `orchestrator/guru.py` — API orchestrator class (`Guru`)
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
│       └── syntactic_disambiguator.py
├── llm/
│   ├── __init__.py
│   └── langchain.py                  # LLM + embedding integration layer
├── orchestrator/
│   ├── __init__.py
│   ├── abstract_orchestrator.py
│   ├── guru.py                       # Main API orchestrator class (Guru)
│   └── live_orchestrator.py
└── data/
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
@InProceedings{10.1007/978-3-031-97207-2_4,
author="Campi, Riccardo
and Pinciroli Vago, Nicol{\`o} Oreste
and Giudici, Mathyas
and Rodriguez-Guisado, Pablo Barrachina
and Brambilla, Marco
and Fraternali, Piero",
editor="Verma, Himanshu
and Bozzon, Alessandro
and Mauri, Andrea
and Yang, Jie",
title="A Graph-Based RAG for Energy Efficiency Question Answering",
booktitle="Web Engineering",
year="2026",
publisher="Springer Nature Switzerland",
address="Cham",
pages="41--55",
abstract="In this work, we investigate the use of Large Language Models (LLMs) within a Graph-based Retrieval Augmented Generation (RAG) architecture for Energy Efficiency (EE) Question Answering. First, the system automatically extracts a Knowledge Graph (KG) from guidance and regulatory documents in the energy field. Then, the generated graph is navigated and reasoned upon to provide users with accurate answers in multiple languages. We implement a human-based validation using the RAGAs framework properties, a validation dataset composed of 101 question-answer pairs, and some domain experts. Results confirm the potential of this architecture and identify its strengths and weaknesses. Validation results show how the system correctly answers in about three out of four of the cases ({\$}{\$}75.2{\backslash}pm 2.7{\backslash}{\%}{\$}{\$}75.2{\textpm}2.7{\%}), with higher results on questions related to more general EE answers (up to {\$}{\$}81.0{\backslash}pm 4.1{\backslash}{\%}{\$}{\$}81.0{\textpm}4.1{\%}), and featuring promising multilingual abilities ({\$}{\$}4.4{\backslash}{\%}{\$}{\$}4.4{\%}accuracy loss due to translation).",
isbn="978-3-031-97207-2"
}
```
