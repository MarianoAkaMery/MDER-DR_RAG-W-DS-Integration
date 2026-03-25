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

## Flusso LLM per il calcolo risparmio gas -> HVAC

Adesso il progetto ha ancora un calcolo deterministico per il numero finale, ma non usa piu le regex per capire se deve partire e per leggere i valori dal testo.

In pratica il flusso e questo:

1. arriva il messaggio utente a `Guru`
2. prima del normale RAG, `Guru` fa una chiamata LLM dedicata
3. questa chiamata usa un prompt strutturato definito in `graph_prompt.py`
4. il modello deve restituire solo un JSON con:
   - se la richiesta e davvero un calcolo `gas -> HVAC`
   - i valori numerici gia normalizzati
   - gli eventuali campi obbligatori mancanti
5. se `should_calculate = true`, il progetto prende quei valori e applica la formula fissa in Python
6. se `should_calculate = false`, il flusso continua normalmente su KB / RAG oppure LLM only

Per me questa e la parte importante:

- l'estrazione dei dati non sta piu nelle regex
- la logica di estrazione adesso vive soprattutto nel prompt
- il calcolo finale resta deterministico e controllabile

### Perche l'ho fatto cosi

Le regex non erano minimamente scalabili.

Appena la frase cambiava un po', o cambiava lingua, o cambiava l'ordine dei pezzi, diventava fragile.

Con questo assetto:

- lascio all'LLM il lavoro sporco di capire intento e parametri
- tengo in Python la formula finale, cosi il numero non dipende dal modello
- posso migliorare l'estrazione toccando il prompt invece di aggiungere altre regex

### Quando si attiva

Si attiva quando il modello capisce che l'utente sta chiedendo una stima o un calcolo economico per passare da un impianto a gas a HVAC / pompa di calore.

La frase tipo che posso usare per provarla e:

```text
Calcola il risparmio economico in caso di sostituzione dell'impianto di riscaldamento da gas a HVAC con 1200 smc annui, prezzo gas 1,05 euro/smc, prezzo elettricita 0,24 euro/kWh, rendimento caldaia 92%, COP 3,8 e costo impianto 9000 euro.
```

Posso provarla anche in inglese con una frase tipo:

```text
Calculate the economic savings for replacing a gas heating system with HVAC using 1200 Smc per year, gas price 1.05 euro/Smc, electricity price 0.24 euro/kWh, boiler efficiency 92%, COP 3.8, and installation cost 9000 euro.
```

### Cosa deve estrarre l'LLM

Obbligatori:

- consumo annuo gas in `Smc`
- prezzo gas in `euro/Smc`
- prezzo elettricita in `euro/kWh`

Opzionali:

- rendimento caldaia in `%` ma normalizzato a decimale, quindi `92% -> 0.92`
- `COP` della pompa di calore
- costo impianto in `euro`

Se mancano i parametri obbligatori, la risposta non inventa numeri: chiede solo i campi mancanti.

### Prompt che governa l'estrazione

Il punto chiave adesso e questo:

- il prompt sta in `knowledge_base/utils/graph_prompt.py`
- la funzione nuova e `extract_gas_to_hvac_savings_inputs(...)`

Questa funzione dice esplicitamente al modello:

- quando deve considerare la richiesta come un vero calcolo `gas_to_hvac_savings`
- quali campi deve estrarre
- come deve normalizzare i valori
- che deve rispondere con solo JSON

Quindi se il professore mi dice "sistemalo da prompt", il primo posto dove guardare e quello.

### Formula usata

La formula finale non l'ho spostata sull'LLM.

Resta in Python cosi:

- calore utile = `Smc * 10.69 * rendimento_caldaia`
- consumo elettrico HVAC = `calore_utile / COP`
- costo annuo gas = `Smc * prezzo_gas`
- costo annuo HVAC = `kWh_elettrici * prezzo_elettricita`
- risparmio annuo = `costo_gas - costo_HVAC`
- payback semplice = `costo_impianto / risparmio_annuo` se il costo impianto e presente e il risparmio e positivo

Default se l'LLM non riceve i valori opzionali:

- rendimento caldaia `90%`
- `COP = 3.2`

### Dove sta il codice

- [guru.py](C:/Users/maria/Desktop/W&DS%20-%20PROJECT/orchestrator/guru.py)
- [static_calculations.py](C:/Users/maria/Desktop/W&DS%20-%20PROJECT/orchestrator/static_calculations.py)
- [graph_prompt.py](C:/Users/maria/Desktop/W&DS%20-%20PROJECT/knowledge_base/utils/graph_prompt.py)

### Come lo ragiono adesso

Se il risultato e sbagliato, io controllo in quest'ordine:

1. il prompt di estrazione in `graph_prompt.py`
2. il JSON che torna dal modello nei log
3. i valori che `Guru` passa al calcolo
4. la formula in `static_calculations.py`

Se il numero finale e sbagliato ma i campi nel JSON sono corretti, allora il problema e nella formula.

Se invece il numero finale e sbagliato perche mancano o sono errati i campi estratti, allora il primo fix da fare e sul prompt, non su regex o parsing testuale locale.

### Casi di test che mi conviene provare

Questa parte per me e fondamentale, perche qui capisco se il prompt sta davvero facendo meglio delle regex.

#### Casi buoni

Caso 1, italiano completo:

```text
Calcola il risparmio economico in caso di sostituzione dell'impianto di riscaldamento da gas a HVAC con 1200 smc annui, prezzo gas 1,05 euro/smc, prezzo elettricita 0,24 euro/kWh, rendimento caldaia 92%, COP 3,8 e costo impianto 9000 euro.
```

Qui mi aspetto:

- `should_calculate = true`
- tutti i campi valorizzati
- `boiler_efficiency = 0.92`
- risposta finale con stima completa e payback

Caso 2, inglese completo:

```text
Calculate the economic savings for replacing a gas heating system with HVAC using 1200 Smc per year, gas price 1.05 euro/Smc, electricity price 0.24 euro/kWh, boiler efficiency 92%, COP 3.8, and installation cost 9000 euro.
```

Qui mi aspetto la stessa cosa del caso sopra, ma in inglese.

Caso 3, ordine sparso dei dati:

```text
Vorrei stimare il risparmio passando a pompa di calore. COP 4, costo impianto 11000 euro, consumo gas 1450 smc anno, elettricita 0,22 euro/kWh, prezzo gas 0,98 euro/smc.
```

Qui mi aspetto:

- `should_calculate = true`
- estrazione corretta anche se i dati non sono nel solito ordine

Caso 4, mancano solo gli opzionali:

```text
Calcola il risparmio da gas a pompa di calore con 1000 smc annui, gas 1,1 euro/smc e luce 0,25 euro/kWh.
```

Qui mi aspetto:

- `should_calculate = true`
- uso dei default:
  - rendimento caldaia `0.90`
  - `COP = 3.2`
- risposta finale con stima completa anche senza costo impianto

#### Casi borderline

Caso 5, manca un campo obbligatorio:

```text
Calcola il risparmio passando da gas a HVAC con 1200 smc annui e prezzo elettricita 0,24 euro/kWh.
```

Qui mi aspetto:

- `should_calculate = true`
- `gas_price_per_smc = null`
- risposta che chiede solo il prezzo gas mancante

Caso 6, richiesta generica senza vero intento di calcolo:

```text
Mi spieghi se una pompa di calore consuma meno di un impianto a gas?
```

Qui mi aspetto:

- `should_calculate = false`
- nessun percorso di calcolo statico
- passaggio al flusso normale KB / RAG

Caso 7, domanda su incentivi e non sul risparmio formula:

```text
Ci sono incentivi in Italia per sostituire la caldaia a gas con una pompa di calore?
```

Qui mi aspetto:

- `should_calculate = false`
- nessuna estrazione numerica
- risposta dal ramo knowledge base

Caso 8, valori ambigui o incompleti:

```text
Vorrei capire il risparmio passando da gas a HVAC, spendo circa 1200 euro l'anno di gas e la luce costa 0,24.
```

Qui mi aspetto:

- o `should_calculate = false`
- oppure `should_calculate = true` ma con campi obbligatori mancanti

Questo caso per me e utile per vedere se il modello inventa conversioni che non deve fare.

#### Casi da tenere d'occhio

Se vedo errori, di solito voglio controllare subito questi punti:

- numeri con virgola italiana tipo `1,05`
- varianti come `mc`, `m3`, `sm3`, `Smc`
- frasi dove prima compare il costo impianto e solo dopo il consumo gas
- messaggi misti italiano + inglese
- richieste che parlano di `pompa di calore`, `HVAC`, `climatizzazione` o `heat pump`

Se questi casi passano, allora vuol dire che il prompt sta iniziando a essere davvero robusto.

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
