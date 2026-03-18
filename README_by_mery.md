# README by Mery

Questi sono appunti miei per riuscire a far partire questo progetto in locale.

Obiettivo pratico:

- far partire la webapp
- usare Ollama in locale
- capire quando il problema e Ollama e quando invece e la knowledge base
- riuscire a lanciare anche gli script Python principali

## 1. Stato attuale

Quello che al momento sono riuscita a far partire:

- `streamlit_ui.py` con Ollama locale: funziona
- `build_knowledge_base.py`: funziona
- `answer_question.py`: funziona, ma solo se la knowledge base si trova nel path che lui si aspetta

Quello che non e automatico / pulito:

- i nomi delle knowledge base non sono allineati bene tra script di build e script di query

## 2. Setup ambiente

Da PowerShell, nella root del progetto:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 3. Ollama in locale

### Installazione

Windows:

- https://ollama.com/download
- https://docs.ollama.com/windows

### Verifica

```powershell
ollama --version
curl http://localhost:11434/api/tags
ollama list
```

### Modelli da scaricare

Quelli che mi sono serviti davvero:

```powershell
ollama pull llama3.2
ollama pull mxbai-embed-large
```

Se voglio provare direttamente il modello da terminale:

```powershell
ollama run llama3.2
```

## 4. Config importante del progetto

File da controllare:

- `private_settings.py`

Valori importanti:

```python
PRIVATE_SETINGS = {
    "LLM_LOCAL": True,
    "LLM_BASE_URL": "http://localhost:11434",
}
```

Se `LLM_LOCAL=True`, il progetto usa Ollama locale.

## 5. Webapp: test piu semplice

Comando:

```powershell
streamlit run .\streamlit_ui.py
```

Impostazioni che ho usato:

- `Provider = ollama`
- `Model = llama3.2`
- `Embedding = mxbai-embed-large`

### Test 1: verificare solo Ollama

Nella sidebar:

- mettere `Use Knowledge Base = off`

Se cosi la chat risponde, allora:

- la webapp funziona
- Ollama funziona
- il problema non e il modello

Questo test l'ho fatto e funziona.

## 6. Build della knowledge base

Comando:

```powershell
python .\build_knowledge_base.py
```

Questo comando, quando ha funzionato, ha creato:

- [knowledge_base/data/Tomato_recipes/rdf_graph.ttl](/C:/Users/maria/Desktop/W&DS%20-%20PROJECT/knowledge_base/data/Tomato_recipes/rdf_graph.ttl)
- [knowledge_base/data/Tomato_recipes/chroma_db](/C:/Users/maria/Desktop/W&DS%20-%20PROJECT/knowledge_base/data/Tomato_recipes/chroma_db)

Quindi il build va a buon fine se:

- Ollama e acceso
- `mxbai-embed-large` e presente

## 7. Errore reale trovato durante il build

Errore incontrato:

```text
ollama._types.ResponseError: model "mxbai-embed-large" not found
```

Significato:

- mancava il modello embeddings in Ollama

Fix:

```powershell
ollama pull mxbai-embed-large
```

## 8. Script `answer_question.py`

Comando:

```powershell
python .\answer_question.py
```

Questo script non funziona subito dopo il build, perche cerca una knowledge base diversa da quella appena creata.

### Knowledge base che il build crea

Il build crea:

- `knowledge_base/data/Tomato_recipes/`

### Knowledge base che `answer_question.py` cerca

Lo script cerca:

- `knowledge_base/data/files_Italy/`

e in particolare:

- [knowledge_base/data/files_Italy/rdf_graph.ttl](/C:/Users/maria/Desktop/W&DS%20-%20PROJECT/knowledge_base/data/files_Italy/rdf_graph.ttl)

### Workaround che ha funzionato

Per far partire `answer_question.py` senza cambiare altro:

```powershell
Copy-Item -Recurse -Force .\knowledge_base\data\Tomato_recipes .\knowledge_base\data\files_Italy
```

Poi:

```powershell
python .\answer_question.py
```

In questo modo lo script e partito correttamente.

## 9. Errore reale trovato su Windows

Errore visto:

```text
urllib.error.URLError: <urlopen error unknown url type: c>
```

Significato pratico:

- il codice stava provando a leggere un file locale Windows
- una libreria lo interpretava come URL
- quindi `C:\...` veniva letto male

Adesso questo problema non mi sta piu bloccando.

## 10. Come distinguere i problemi

### Se con `Use Knowledge Base = off` la UI risponde

Allora:

- Ollama funziona
- la webapp funziona

### Se con `Use Knowledge Base = on` la UI non risponde

Allora probabilmente manca la knowledge base che la UI sta cercando.

### Se `build_knowledge_base.py` si ferma

Controllare:

- Ollama acceso
- modello `mxbai-embed-large` scaricato

### Se `answer_question.py` si ferma con `Knowledge base not found`

Controllare il path della KB che lui si aspetta.

## 11. Ordine giusto da seguire

Per non perdere tempo, l'ordine migliore per me e questo:

1. attivare il venv
2. controllare Ollama
3. fare `ollama pull llama3.2`
4. fare `ollama pull mxbai-embed-large`
5. testare la UI con `Use Knowledge Base = off`
6. lanciare `python .\build_knowledge_base.py`
7. se serve usare il workaround per `files_Italy`
8. lanciare `python .\answer_question.py`

## 12. Comandi che mi servono davvero

```powershell
.\.venv\Scripts\Activate.ps1
ollama --version
curl http://localhost:11434/api/tags
ollama list
ollama pull llama3.2
ollama pull mxbai-embed-large
streamlit run .\streamlit_ui.py
python .\build_knowledge_base.py
Copy-Item -Recurse -Force .\knowledge_base\data\Tomato_recipes .\knowledge_base\data\files_Italy
python .\answer_question.py
```

## 13. Fonti utili su Ollama

- https://ollama.com/download
- https://docs.ollama.com/windows
- https://docs.ollama.com/quickstart
- https://docs.ollama.com/api/introduction
- https://ollama.com/library/llama3.2
