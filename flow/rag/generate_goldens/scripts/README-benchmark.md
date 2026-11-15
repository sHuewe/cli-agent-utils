# Gemeinsamer DeepEval-Benchmark mit AgentWrapper

Das [Notebook](../benchmark.ipynb) verwendet dieselben exportierten
`rag-goldens/deepeval-goldens.json` für alle Agenten. Die Agenten werden
**ohne DeepEval-Abhängigkeit** ausgeführt; DeepEval übernimmt danach
ausschließlich die Bewertung der Antworten und optional der tatsächlich
gefundenen Passagen.

## Schnittstelle für jedes Team

Ein Team stellt eine importierbare Python-Klasse mit drei asynchronen
Methoden bereit:

```python
# team_b/benchmark.py
class TeamBWrapper:
    def __init__(self, endpoint: str):
        self.endpoint = endpoint
        self.agent = None

    async def start(self):
        # Einmalig Modelle, Verbindungen und Index initialisieren.
        self.agent = await connect(self.endpoint)

    async def answer(self, question: str):
        # Jede Frage in einer frischen Unterhaltung behandeln.
        return await self.agent.ask_new_conversation(question)

    async def close(self):
        if self.agent is not None:
            await self.agent.close()
            self.agent = None
```

`answer()` gibt entweder einen nichtleeren String oder ein Dictionary
`{"answer": str, "retrieval_context": list[str]}` zurück.
`retrieval_context` darf ausschließlich **tatsächlich abgerufene**
Passagen enthalten. Ohne Retrieval-Kontext werden fachliche Metriken
weiterhin ausgewertet.

`AgentWrapper` ist ein strukturelles Python-`Protocol` zur Beschreibung
dieser drei Methoden. **Keine Vererbung oder Import aus dem Notebook**
ist erforderlich. Das Team ist selbst für die Unabhängigkeit aufeinander-
folgender Fragen zuständig. Jede Frage muss ohne Konversationswissen
aus anderen Goldens beantwortet werden.

## Teilnehmer konfigurieren

Die Team-Module müssen im Jupyter-Python-Environment installiert sein.
Im Notebook genügt:

```python
AGENTS = {
    "team-a": {
        "entrypoint": "team_a.benchmark:TeamAWrapper",
        "revision": "commit-a1b2c3",
    },
    "team-b": {
        "entrypoint": "team_b.benchmark:TeamBWrapper",
        "revision": "commit-d4e5f6",
        "kwargs": {"endpoint": "http://localhost:8080"},
    },
}
```

`entrypoint` bezeichnet die Python-Klasse, `kwargs` ihre optionalen
Konstruktorparameter. `create_wrapper(spec)` erzeugt **nur die Instanz**.
Der Benchmark ruft `start()` beim ersten nicht gecachten Golden auf,
verwendet denselben Wrapper für weitere Fragen und garantiert ein
`close()` am Ende. Nach einem Fehler oder Timeout wird der beschädigte
Wrapper geschlossen und vor der nächsten Frage neu aufgebaut.

Der mitgelieferte Eintrag `builtin:cli-agent` ist optional und dient
als Beispiel. Er erstellt den SDK-Agenten **einmal** beim `start()` und
ruft `agent.reset()` vor jeder Frage auf; dabei bleiben Modell- und
MCP-Verbindungen grundsätzlich bestehen. Andere Teams brauchen kein
`cli-agent` zu installieren.

## Bewertung

```bash
python -m pip install "deepeval>=4,<5" pandas jupyterlab ipykernel
jupyter lab flow/rag/generate_goldens/benchmark.ipynb
```

Jupyter wird aus dem Workspace mit `rag-goldens/deepeval-goldens.json`
gestartet. `MAX_CASES=3` testet zuerst drei Goldens;
`MAX_CASES=None` testet alle.

DeepEval lädt die unveränderten Referenzantworten, erstellt aus den
Ergebnissen `LLMTestCase` und bewertet mit `evaluate()`:
fachliche Korrektheit und Relevanz für alle erfolgreichen Antworten,
Faithfulness/Recall/Precision/Unsicherheit nur bei vollständigem
tatsächlichen Retrieval-Kontext, optional Stilkonformität je Team.

Es gibt **kein** DeepEval-spezifisches Interface oder automatisches
Tracing im Wrapper. Die Referenzantwort wird niemals an `answer()`
übergeben.

## Fairness, Fehler und Caching

- Alle Teams verwenden dieselben Goldens, identische Judge-Metriken,
  dieselbe Judge-Modellkonfiguration und einen festgelegten Korpusstand
- Der Benchmark zeigt die Zahl erfolgreich beantworteter Goldens und
  fehlgeschlagener Fragen; Durchschnittswerte mit unterschiedlicher
  Abdeckung sind nur eingeschränkt vergleichbar
- Ergebnisse werden pro Agent-ID, Modul, Revision, `kwargs`, Golden und
  `CACHE_EPOCH` getrennt gecacht. Für den eingebauten SDK-Wrapper
  werden zusätzlich Konfigurationsdateien berücksichtigt
- Nach einer Änderung von Agent, Prompt, Index oder Modell die Revision
  bzw. `CACHE_EPOCH` ändern oder `FRESH_RESPONSES=True` setzen
- Das Speichern erfolgt atomar mit privaten Dateirechten.
  `FRESH_EVALUATION=True` deaktiviert unabhängig davon das
  DeepEval-Judge-Cache-Replay
- Bei Sync-Frameworks sollte der Wrapper die Aufrufe selbst asynchron
  kapseln. Async-Cancellation muss bei laufenden Modellaufrufen sauber
  abgewickelt werden

Antwort-Caches und Judge-Reports können vertrauliche Daten enthalten.
Sie gehören nicht in die Versionsverwaltung.
