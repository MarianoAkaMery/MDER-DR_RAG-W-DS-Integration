# Energenius RAG

RAG project for answering questions over energy-efficiency knowledge bases.

## Runtime KBs

The application now uses these knowledge bases:

- `Italy`
- `Switzerland`
- `Europe`
- `Generic`

At runtime they are resolved from:

- imported assets in `home/mbrambilla/EnergeniusRAG/knowledge_base/files_<name>`
- local fallback assets in `knowledge_base/data/files_<name>`

If the imported assets are present, they are used automatically. You do not need to rebuild the vector DB just to run the app.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Configure `private_settings.py` for either Ollama or OpenAI.

## Run the UI

```powershell
streamlit run .\streamlit_ui.py
```

Use one of the supported knowledge bases from the sidebar: `Italy`, `Switzerland`, `Europe`, `Generic`.

## Run a direct test

```powershell
python .\answer_question.py
```

This uses the `Italy` knowledge base by default.

## Rebuild a KB only if needed

Rebuilding is optional. Do it only if you want to regenerate graph/vector assets from new URLs.

```powershell
python .\build_knowledge_base.py --knowledge-base files_Italy --url "https://example.com/doc1" --url "https://example.com/doc2"
```

Artifacts are written under `knowledge_base/data/<knowledge-base>/`.

## Benchmark

Put `benchmark/benchmark_dataset.csv` in place, then run:

```powershell
python .\run_benchmark.py
```

The dataset `Region` column must contain KB names compatible with `Guru.set_knowledge_base(...)`, for example `Italy` or `Switzerland`.
