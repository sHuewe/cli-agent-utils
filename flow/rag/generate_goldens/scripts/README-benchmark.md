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
mit `answer: str` und optional `retrieval_context: list[str]` sowie
`tools_called: list[dict]` zurück. `retrieval_context` darf ausschließlich
**tatsächlich abgerufene** Passagen enthalten. Eine leere Liste ist
gültig; ohne Retrieval-Kontext werden fachliche Metriken trotzdem bewertet.

Ein Tool-Eintrag enthält mindestens `name`. Weitere optionale Felder:
`call_id`, `status`, `duration_ms` und `input_parameters` (Dictionary).
`tools_called=None` bedeutet **nicht gemeldet**, `[]` bedeutet
**beobachtet, aber kein Tool aufgerufen**. Parameter können Geheimnisse
enthalten und werden im privaten Cache gespeichert. Sie sollten nur
übergeben werden, wenn die Verwendung im Benchmark freigegeben ist.

Die mitgelieferte Datei [`cli_agent_wrapper.py`](../cli_agent_wrapper.py)
enthält **sämtlichen cli-agent-spezifischen Code**: SDK-Initialisierung,
Konfiguration, Reset je Golden, Knowledge-Passagen und Tool-Telemetrie.
Ihr Wrapper nutzt opt-in `with_tool_trace(include_arguments=True)`,
wenn `include_tool_arguments=True` als Konstruktorargument gesetzt ist.
Tool-Ergebnisse bleiben ausgeschlossen. Die Argument-Redaction des SDK
ist best effort; für vertrauliche Daten sollte die Option deaktiviert bleiben.

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

Auch cli-agent ist jetzt ein **normaler Import** wie alle anderen Teams:

```python
"cli-agent": {
    "entrypoint": "flow.rag.generate_goldens.cli_agent_wrapper:CliAgentWrapper",
    "revision": "sdk-baseline-v1",
    "kwargs": {
        "workspace": str(WORKSPACE),
        "include_tool_arguments": True,
        # Optional: "config_file": "config.toml",
        # Optional: "admin_config_file": "admin.toml",
        # Optional: "system_prompt": "Answer factually...",
        # Optional: "approve_tools": ["vector__knowledge_search"],
        # Optional: "redact_keys": ["business_private_field"],
    },
},
```

Das Notebook enthält **weder cli-agent-Imports noch besondere
Fallunterscheidungen**. Der Wrapper initialisiert den SDK-Agenten einmal
beim `start()` und ruft `agent.reset()` vor jeder Frage auf. Andere Teams
brauchen keine cli-agent-Installation, sofern sie den cli-agent-Wrapper
nicht ausführen. Die Namespacemodule unter `flow.rag.generate_goldens`
sind vom Workspace-Root importierbar.

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

## Bewertung von Werkzeugaufrufen

DeepEval unterstützt `ToolCorrectnessMetric`, aber nur Testfälle mit
explizit erwarteten Werkzeugen können sinnvoll gegen ein Soll bewertet
werden. Unsere generierten Goldens enthalten bisher **keine**
`expected_tools`. Das Notebook speichert und zählt `tools_called`
dennoch, führt `ToolCorrectnessMetric` aber nur aus, wenn sowohl
beobachtete Aufrufe als auch `golden.expected_tools` vorhanden sind.
Mit `TOOL_COMPARE_ARGUMENTS=True` werden zusätzlich die Argumente
verglichen; dies setzt entsprechende tatsächlich verfügbare, freigegebene
Argumente auf beiden Seiten voraus.

Die Vergleichstabelle führt `tool_telemetry_cases`,
`total_tool_calls`, `tool_error_calls`,
`tool_calls_with_arguments` und `tool_correctness_cases` auf.
Unterschiedliche Agenten können völlig verschiedene technische Tools
verwenden. Vorgeschriebene Toolnamen sind daher nur fair, wenn sie auf
alle Teilnehmer anwendbar sind.

## Fairness, Fehler und Caching

- Alle Teams verwenden dieselben Goldens, identische Judge-Metriken,
  dieselbe Judge-Modellkonfiguration und einen festgelegten Korpusstand
- Der Benchmark zeigt die Zahl erfolgreich beantworteter Goldens und
  fehlgeschlagener Fragen; Durchschnittswerte mit unterschiedlicher
  Abdeckung sind nur eingeschränkt vergleichbar
- Ergebnisse werden pro Agent-ID, Modul, Revision, `kwargs`, Golden und
  `CACHE_EPOCH` getrennt gecacht. Optional kann **jedes Team**
  `"cache_files": ["path/to/agent.toml", "path/to/prompt.md"]` angeben,
  um die Inhalte dieser Konfigurationsdateien in den Schlüssel aufzunehmen.
  Es gibt keinen Sonderfall für cli-agent mehr. Wird ein Prompt oder
  eine Datei nicht eingetragen, muss eine neue `revision` verwendet werden
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
