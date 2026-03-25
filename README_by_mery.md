# README by Mery

Questi sono i miei appunti operativi per usare il progetto in locale senza perdere tempo sulle stesse cose ogni volta.

## Stato attuale

Adesso il progetto legge direttamente le knowledge base che ho importato da:

- `home/mbrambilla/EnergeniusRAG/knowledge_base/files_Italy`
- `home/mbrambilla/EnergeniusRAG/knowledge_base/files_Switzerland`
- `home/mbrambilla/EnergeniusRAG/knowledge_base/files_Europe`
- `home/mbrambilla/EnergeniusRAG/knowledge_base/files_Generic`

Per me questo significa:

- non devo copiare `Tomato_recipes` in `files_Italy`
- non devo ricostruire il DB vettoriale per usare la knowledge gia presente
- devo usare `build_knowledge_base.py` solo per rigenerare una KB da nuove URL

## Setup ambiente

Quando parto da zero, nella root del progetto faccio:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Ollama in locale

Per controllare che sia tutto a posto faccio:

```powershell
ollama --version
curl http://localhost:11434/api/tags
ollama list
```

I modelli che mi servono sono:

```powershell
ollama pull llama3.2
ollama pull mxbai-embed-large
```

## Config importante

Devo controllare `private_settings.py` e tenerlo cosi:

```python
PRIVATE_SETINGS = {
    "LLM_LOCAL": True,
    "LLM_BASE_URL": "http://localhost:11434",
}
```

Se `LLM_LOCAL=True`, il progetto usa Ollama locale.

## Webapp

Per avviare la webapp faccio:

```powershell
streamlit run .\streamlit_ui.py
```

Le impostazioni che sto usando sono:

- `Provider = ollama`
- `Model = llama3.2`
- `Embedding = mxbai-embed-large`
- `Language = Italiano`
- `Knowledge Base = Italy`

### Test rapido che faccio io

1. metto `Use Knowledge Base = off`
2. faccio una domanda generica per vedere se la chat risponde
3. rimetto `Use Knowledge Base = on`
4. faccio una domanda sul dominio energia

Se nei log vedo `Loading graph...OK`, per me vuol dire che la KB e stata caricata.

## Build knowledge base

Per usare la KB che ho gia importato non devo fare nessun build.

Uso `build_knowledge_base.py` solo se devo rigenerare una knowledge base da nuove URL.

Esempio:

```powershell
python .\build_knowledge_base.py --knowledge-base files_Italy --url "https://example.com/doc1" --url "https://example.com/doc2"
```

## Test diretto da script

Se voglio fare una prova veloce fuori dalla webapp faccio:

```powershell
python .\answer_question.py
```

Questo script usa `Italy` come KB di default.

## Function call statica: risparmio gas -> HVAC

Ho aggiunto un percorso statico prima del normale RAG per fare un calcolo deterministico del risparmio economico in un caso specifico:

- sostituzione di un impianto di riscaldamento a gas con HVAC / pompa di calore

Questa parte non usa la KB per fare il numero finale: intercetta la richiesta, estrae i parametri dal testo e applica una formula fissa.

### Quando si attiva

Si attiva solo se nel messaggio c'e chiaramente una richiesta di calcolo o stima e compaiono insieme:

- gas
- HVAC oppure `pompa di calore`
- contesto di risparmio, costo o bolletta

La frase tipo che posso usare per provarla e:

```text
Calcola il risparmio economico in caso di sostituzione dell'impianto di riscaldamento da gas a HVAC con 1200 smc annui, prezzo gas 1,05 euro/smc, prezzo elettricita 0,24 euro/kWh, rendimento caldaia 92%, COP 3,8 e costo impianto 9000 euro.
```

Posso provarla anche in inglese con una frase tipo:

```text
Calculate the economic savings for replacing a gas heating system with HVAC using 1200 Smc per year, gas price 1.05 euro/Smc, electricity price 0.24 euro/kWh, boiler efficiency 92%, COP 3.8, and installation cost 9000 euro.
```

### Parametri che legge dal testo

Obbligatori:

- consumo annuo gas in `Smc`
- prezzo gas in `euro/Smc`
- prezzo elettricita in `euro/kWh`

Opzionali:

- rendimento caldaia in `%`
- `COP` della pompa di calore
- costo impianto in `euro`

Se mancano i parametri obbligatori, la chat mi chiede solo quelli mancanti.

### Formula usata

- calore utile = `Smc * 10.69 * rendimento_caldaia`
- consumo elettrico HVAC = `calore_utile / COP`
- costo annuo gas = `Smc * prezzo_gas`
- costo annuo HVAC = `kWh_elettrici * prezzo_elettricita`
- risparmio annuo = `costo_gas - costo_HVAC`
- payback semplice = `costo_impianto / risparmio_annuo` se il costo impianto e presente e il risparmio e positivo

Default se non li specifico:

- rendimento caldaia `90%`
- `COP = 3.2`

### Dove sta il codice

- [static_calculations.py](C:/Users/maria/Desktop/W&DS%20-%20PROJECT/orchestrator/static_calculations.py)
- [guru.py](C:/Users/maria/Desktop/W&DS%20-%20PROJECT/orchestrator/guru.py)

## Comandi che mi servono davvero

```powershell
.\.venv\Scripts\Activate.ps1
ollama --version
curl http://localhost:11434/api/tags
ollama list
ollama pull llama3.2
ollama pull mxbai-embed-large
streamlit run .\streamlit_ui.py
python .\answer_question.py
```

## Fonti utili su Ollama

- https://ollama.com/download
- https://docs.ollama.com/windows
- https://docs.ollama.com/quickstart
- https://docs.ollama.com/api/introduction
- https://ollama.com/library/llama3.2
