# Topic 13 — Customer Complaint Triage Graph  (TA2)

## Prerequisites

1. **Ollama running** in the background:
   ```bash
   ollama serve
   ollama pull qwen2.5:3b
   ollama pull nomic-embed-text
   ```

2. **Python 3.10+** with dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## One-command run (non-interactive — captures all traces)

```bash
cd ta2
python seed_db.py && python rag_setup.py && python triage_graph_ta2.py --auto-approve 2>&1 | tee ../traces/ta2_traces.txt
```

## Step-by-step

```bash
cd ta2
python seed_db.py            # Initialise SQLite DB (complaints.db) + seed 3 customers
python rag_setup.py          # Build Chroma vector index from corpus/policy_faq.txt
python triage_graph_ta2.py   # Run all demo sections (interactive HITL)
# OR
python triage_graph_ta2.py --auto-approve   # Non-interactive trace mode
```

## What runs

| Section | What's demonstrated | SOP component |
|---------|---------------------|---------------|
| 1. Main cases | 6 complaints routed (3 clean + 2 ambiguous + 1 angry) | EV, U4-2 |
| 2. Short-term memory | Multi-turn with/without `thread_id` (amnesia shown) | U3-1 |
| 3. Long-term memory | Restart demo: profile loaded from SQLite after process kill | U3-2 |
| 4. RAG demo | k=1 vs k=3 retrieval + unanswerable question | U3-3 |
| 5. Tool failure | Injected exception → failure_handler → safe fallback | U3-4 |
| 6. Challenge analysis | LLM call count, hop counts, escalation table | U4-4 |

## Files

```
ta2/
├── corpus/policy_faq.txt        10-chunk RAG corpus
├── seed_db.py                   SQLite init + seed (complaints.db)
├── rag_setup.py                 Chroma index builder (chroma_db/)
├── triage_graph_ta2.py          Main graph (all units)
└── requirements.txt
```

## Allowed models / tools

| Component | Model / Tool |
|-----------|-------------|
| Classification & responses | `qwen2.5:3b` via Ollama |
| Embeddings | `nomic-embed-text` via Ollama |
| Vector store | Chroma (persisted to `./chroma_db`) |
| Short-term memory | LangGraph `SqliteSaver` (`checkpoints.db`) |
| Long-term memory | SQLite (`complaints.db`) |
| Graph orchestration | LangGraph |
