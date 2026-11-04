# Agentic AI — Customer Complaint Triage Graph

A multi-agent customer-support triage system built with **LangGraph**, running entirely on **local models via Ollama**. Incoming complaints are classified (billing / technical / general / needs-clarification), grounded in company policy through RAG, answered by a specialist agent, and escalated to a human reviewer when the customer is angry or the case is ambiguous.

The project is built in two stages:

| Stage | Folder | What it is |
|-------|--------|-----------|
| **TA1** | [`ta1/`](ta1) | Frozen baseline: a single classify node using self-consistency voting, routed to four simple responders. |
| **TA2** | [`ta2/`](ta2) | Extended system: adds short-term memory, long-term memory, RAG, tool-failure recovery, specialist agents, hop limits and human-in-the-loop review. |

---

## Features

- **Self-consistency classification**: the classifier runs 3 times at `temperature=0.7` and takes a majority vote. A 3-way split is treated as ambiguity and routed to a clarification agent. No "are you sure?" meta-prompt is used.
- **Short-term memory**: a LangGraph `SqliteSaver` checkpointer keyed by `thread_id` lets follow-up messages in the same conversation recall earlier details.
- **Long-term memory**: SQLite tables (`complaints`, `profiles`) persist customer history and profile across process restarts.
- **RAG over policy documents**: Chroma vector store and `nomic-embed-text` embeddings over a 10-chunk policy/FAQ corpus, with a grounded "I don't know based on our documentation" fallback.
- **Tool-failure recovery**: if classification throws (for example Ollama is down), a `failure_handler` node returns a safe fallback response instead of crashing.
- **Multi-agent coordination**: a supervisor routes to Billing, Technical, General and Clarification specialists, with a `MAX_HOPS` guard.
- **Human-in-the-loop oversight**: anger keywords or ambiguity trigger a human review step with an APPROVE / REJECT path.
- **Measured analysis**: LLM call count, hop count and wall-clock time are reported per case.

---

## Architecture (TA2)

```
START
  └─► load_history      SQLite: customer profile + last 3 complaints
        └─► rag         Chroma: top-k policy chunks
              └─► classify   3x sampled vote, hop counter, try/except
                    ├─► billing_agent ───────┐
                    ├─► technical_agent ─────┤
                    ├─► general_agent ───────┼─► escalation_check ─► human_review? ─► END
                    ├─► needs_clarification ─┘
                    └─► failure_handler ─────────────────────────────────────────► END
```

See [`DOCUMENTATION.md`](DOCUMENTATION.md) for a node-by-node explanation.

---

## Repository structure

```
Agentic-Ai-/
├── ta1/
│   └── triage_graph.py            # TA1 frozen baseline
├── ta2/
│   ├── triage_graph_ta2.py        # TA2 main graph + demo suites
│   ├── rag_setup.py               # Builds/loads the Chroma index
│   ├── seed_db.py                 # SQLite schema, seed data, memory helpers
│   ├── corpus/policy_faq.txt      # 10-chunk policy/FAQ knowledge base
│   ├── requirements.txt
│   ├── README.md                  # TA2 quick-start
│   ├── complaints.db              # (generated) long-term memory
│   ├── checkpoints.db             # (generated) LangGraph checkpoints
│   └── chroma_db/                 # (generated) vector index
├── traces/                        # Captured run outputs used as evidence
├── report/                        # Final report (markdown, PDF) + PDF generators
├── report.pdf
├── Topic13_Beginner_Explainer_Guide.pdf
└── .gitignore
```

---

## Prerequisites

- **Python 3.10+**
- **[Ollama](https://ollama.com)** installed and running
- Roughly 3 GB of free disk for the models

Pull the two models used:

```bash
ollama serve                 # keep running in a separate terminal
ollama pull qwen2.5:3b       # chat / classification model
ollama pull nomic-embed-text # embedding model (TA2 only)
```

## Installation

```bash
git clone https://github.com/Saiuk-dev/Agentic-Ai-.git
cd Agentic-Ai-

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r ta2/requirements.txt
```

`ta1` needs only `langgraph` and `langchain-ollama`, which are already included in the TA2 requirements.

---

## Usage

### Run TA1 (baseline)

```bash
cd ta1
python triage_graph.py
```

Runs five test complaints (3 clean, 2 ambiguous) and prints the vote breakdown, category, reasoning and response for each.

### Run TA2 (extended)

```bash
cd ta2

# One-time setup
python seed_db.py      # create complaints.db and seed 3 customers
python rag_setup.py    # embed policy_faq.txt into chroma_db/

# Run all demo sections
python triage_graph_ta2.py                  # interactive: you type APPROVE / REJECT: <reason>
python triage_graph_ta2.py --auto-approve   # non-interactive: for trace capture
```

One-command version that also saves the full trace:

```bash
cd ta2
python seed_db.py && python rag_setup.py && \
python triage_graph_ta2.py --auto-approve 2>&1 | tee ../traces/ta2_traces.txt
```

> **Important:** run TA2 scripts from inside `ta2/`. The modules import each other (`from seed_db import ...`) by relative name.

### What the TA2 run demonstrates

| # | Section | Shows | Trace file |
|---|---------|-------|-----------|
| 1 | Main cases | 6 complaints: 3 clean, 2 ambiguous, 1 angry | `traces/ta2_traces.txt` |
| 2 | Short-term memory | Same follow-up with and without `thread_id` | `memory_with.txt`, `memory_without.txt` |
| 3 | Long-term memory | Profile and history loaded from SQLite after "restart" | `restart_demo.txt` |
| 4 | RAG | k=1 vs k=3 retrieval, plus an unanswerable question | `rag_k1_vs_k3.txt` |
| 5 | Tool failure | Injected exception, safe fallback | `tool_failure.txt` |
| 6 | Oversight | Human APPROVE and REJECT paths | `escalation_approved.txt`, `escalation_rejected.txt` |
| 7 | Challenge analysis | LLM calls, hops, escalation per case | `challenge_analysis.txt` |

---

## Configuration

Settings live as constants at the top of `ta2/triage_graph_ta2.py`:

| Constant | Default | Purpose |
|----------|---------|---------|
| `MAX_HOPS` | `3` | Hop ceiling for the classify node |
| `RAG_K` | `3` | Number of policy chunks retrieved per query |
| `ANGER_KEYWORDS` | set of 12 words | Triggers automatic human escalation |
| model name | `qwen2.5:3b` | Change in the `ChatOllama(...)` calls to use another Ollama model |

Embedding model and collection name are set in `ta2/rag_setup.py` (`EMBED_MODEL`, `COLLECTION`).

---

## Tech stack

| Component | Technology |
|-----------|-----------|
| Orchestration | LangGraph |
| LLM | `qwen2.5:3b` via Ollama (`langchain-ollama`) |
| Embeddings | `nomic-embed-text` via Ollama |
| Vector store | Chroma (`langchain-chroma`) |
| Short-term memory | LangGraph `SqliteSaver` (`checkpoints.db`) |
| Long-term memory | SQLite (`complaints.db`) |

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---------|--------------------|
| `Connection refused` / classify falls back to `failure_handler` | Ollama isn't running. Start `ollama serve`. |
| `model "qwen2.5:3b" not found` | Run `ollama pull qwen2.5:3b`. |
| Embedding errors in `rag_setup.py` | Run `ollama pull nomic-embed-text`. |
| `ModuleNotFoundError: seed_db` | You're not inside the `ta2/` directory. |
| Empty RAG context | Run `python rag_setup.py` first to build `chroma_db/`. |
| Wiped customer history | `seed_db.py` drops and recreates tables each run; don't re-run it if you want to keep data. |

---

## Further reading

- [`DOCUMENTATION.md`](DOCUMENTATION.md): detailed technical documentation
- [`report/report.md`](report/report.md): final report with evaluation (TA1 vs TA2)
- `Topic13_Beginner_Explainer_Guide.pdf`: beginner-friendly explainer

## License

No license has been specified. Add one (for example MIT) if you want others to reuse the code.
