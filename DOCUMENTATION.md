# Technical Documentation — Customer Complaint Triage Graph

This document explains how the code in this repository works: the design, each module and node, the data stores, the state schema, the demo suites, and known limitations. For setup and quick-start, see [`README.md`](README.md).

## Table of contents

1. [Overview](#1-overview)
2. [Design concepts](#2-design-concepts)
3. [TA1: baseline](#3-ta1-baseline)
4. [TA2: extended system](#4-ta2-extended-system)
5. [Data stores](#5-data-stores)
6. [RAG corpus and retrieval](#6-rag-corpus-and-retrieval)
7. [Demo suites and traces](#7-demo-suites-and-traces)
8. [Evaluation summary](#8-evaluation-summary)
9. [Extending the system](#9-extending-the-system)
10. [Known limitations and observations](#10-known-limitations-and-observations)
11. [Glossary](#11-glossary)

---

## 1. Overview

The system triages free-text customer complaints. For each complaint it:

1. Loads what is already known about the customer.
2. Retrieves relevant company policy.
3. Classifies the complaint with a self-consistency vote.
4. Routes it to a specialist agent that drafts a reply.
5. Decides whether a human must review the reply before it is sent.

All inference is local: **`qwen2.5:3b`** for text generation and **`nomic-embed-text`** for embeddings, both served by Ollama. Orchestration uses **LangGraph** `StateGraph`.

The code was written for a course assignment (Topic 13, with component IDs such as U3-1 … U4-4 and EV appearing in comments). These IDs map to features as follows:

| ID | Feature | Where |
|----|---------|-------|
| U3-1 | Short-term memory | `SqliteSaver` + `thread_history` |
| U3-2 | Long-term memory | `seed_db.py`, `load_history_node` |
| U3-3 | RAG | `rag_setup.py`, `rag_node` |
| U3-4 | Tool-failure handling | `classify_node` try/except, `failure_handler` |
| U4-1 | Role design | Specialist agent nodes |
| U4-2 | Coordination | `route_by_category`, `MAX_HOPS` |
| U4-3 | Oversight | `escalation_check`, `human_review` |
| U4-4 | Challenge analysis | `format_challenge_table`, per-case metrics |
| EV | Evaluation | TA1 vs TA2 comparison in `report/report.md` |

---

## 2. Design concepts

### 2.1 Self-consistency instead of self-doubt

A small 3B model over-triggers if asked "are you sure?". Instead, the classification prompt is run **3 times at `temperature=0.7`**, and the votes are tallied:

- **2 or 3 votes agree** → confident; use the majority category.
- **All 3 differ** (billing / technical / general) → ambiguous; category becomes `needs_clarification`.

The disagreement itself is the uncertainty signal. No extra LLM call is needed to measure confidence.

### 2.2 Two model handles

| Handle | Temperature | Used for |
|--------|-------------|----------|
| `llm` | 0 | Response generation: deterministic, consistent tone |
| `llm_sampling` | 0.7 | Classification votes only: sampling needs variance, otherwise all 3 calls would be identical |

### 2.3 Layered context injection

Specialist prompts are assembled from up to three optional blocks, always placed before the complaint:

1. **Company Policy & FAQ Context** (RAG)
2. **Customer Profile & Past Issues** (long-term memory)
3. **Conversation Thread (Recent Turns)** (short-term memory, last 4 turns only, to protect the small model's context window)

---

## 3. TA1: baseline

**File:** `ta1/triage_graph.py` (frozen, kept unchanged as the evaluation baseline)

### Graph

```
classify_with_consistency
        │ (conditional edge on state["category"])
  ┌─────┼──────────┬────────────────────┐
billing technical general   needs_clarification
  │       │          │              │
 END     END        END            END
```

### State (`TriageState`)

| Field | Type | Meaning |
|-------|------|---------|
| `complaint` | str | Raw customer text |
| `category` | str | `billing` / `technical` / `general` / `needs_clarification` |
| `confidence_note` | str | One-sentence reasoning from the matching vote |
| `votes` | str | Tally string, for example `billing:2, technical:1` |
| `response` | str | Final customer-facing reply |

### Functions

| Function | Description |
|----------|-------------|
| `_classify_once(complaint, model)` | Sends `CLASSIFY_PROMPT`, parses `CATEGORY:` and `REASON:` lines. Defaults to `general` if the model output can't be parsed. Kept separate so single-shot behaviour can be restored easily. |
| `classify_with_consistency(state)` | Calls `_classify_once` 3× with `llm_sampling`, tallies with `Counter`, returns majority or `needs_clarification`. |
| `_respond(state, department, tone_hint)` | Shared helper that asks `llm` for a 2–3 sentence reply. |
| `respond_billing / respond_technical / respond_general` | Thin wrappers with department-specific tone hints. |
| `needs_clarification(state)` | Asks the customer a single friendly question to disambiguate, without guessing. |
| `route_by_category(state)` | Conditional-edge function; returns the category string used as the next node key. |

### Test set

Five built-in cases: three clean (billing, technical, general) and two ambiguous (premium upgrade charged but not activated; account access that might be payment or login).

TA1 makes **4 LLM calls** per complaint (3 votes + 1 response).

---

## 4. TA2: extended system

**Main file:** `ta2/triage_graph_ta2.py`

### 4.1 Graph topology

```
START → load_history → rag → classify ─┬─► billing_agent ─────────┐
                                       ├─► technical_agent ───────┤
                                       ├─► general_agent ─────────┼─► escalation_check ─┬─► human_review ─► END
                                       ├─► needs_clarification_agent ┘                  └─► END
                                       └─► failure_handler ─► END
```

`failure_handler` deliberately bypasses escalation, since there is no meaningful draft to review.

### 4.2 State schema

| Field | Type | Purpose |
|-------|------|---------|
| `complaint` | str | Input text |
| `customer_id` | str | Key into SQLite stores |
| `conversation_id` | str | Used as the default `thread_id` |
| `rag_k` | int | Per-run retrieval depth override |
| `thread_history` | `Annotated[list[str], operator.add]` | Short-term memory. The `operator.add` reducer **appends** each node's list instead of overwriting, so turns accumulate across invocations when a checkpointer is used |
| `customer_history` | str | Formatted profile + last 3 complaints |
| `rag_context` | str | Retrieved policy text |
| `category` | str | Classifier result, or the sentinel `__tool_error__` |
| `votes` | str | Vote tally, or `hop_limit` |
| `confidence_note` | str | Reason from the winning vote |
| `hop_count` | int | Incremented by `classify_node` |
| `tool_error` | str | Non-empty if classification raised |
| `escalated` | bool | Set by `escalation_check` |
| `escalation_reason` | str | Human-readable trigger |
| `human_decision` | str | `APPROVE` or `REJECT: <reason>` |
| `human_override` | str | Pre-supplied decision, used for scripted demos |
| `response` | str | Final reply |
| `llm_calls` | int | Running count for challenge analysis |
| `wall_start` | float | Start timestamp |

### 4.3 Node reference

#### `load_history_node` (U3-2)
Reads the customer's profile and last 3 complaints from SQLite via `seed_db.load_profile` and `load_customer_history`, merges them into `customer_history`, and appends `"Customer: <complaint>"` to `thread_history`.

#### `rag_node` (U3-3)
Calls `rag_setup.retrieve(complaint, k)` where `k` comes from `state["rag_k"]` (default 3). Stores formatted chunks in `rag_context`.

#### `classify_node` (U3-4, U4-2)
1. Increments `hop_count` and prints `hop=n/MAX_HOPS`.
2. If `hop >= MAX_HOPS`, forces `needs_clarification` with `votes="hop_limit"`.
3. Otherwise runs the 3-vote self-consistency classification inside `try/except`.
4. On success, returns the category, vote tally and reasoning, and adds 3 to `llm_calls`.
5. On any exception, returns `category="__tool_error__"` and the error text in `tool_error`.

#### Specialist agents (U4-1)

All four build their prompt through `_build_agent_prompt` (except clarification, which uses a short standalone prompt) and append their reply to `thread_history`.

| Agent | Role | Behaviour hints in prompt |
|-------|------|---------------------------|
| `billing_agent` | Payments, invoices, refunds | Cite policy (for example 5–7 business days for duplicate refunds); restate invoice number/amount if asked earlier in thread |
| `technical_agent` | Bugs, crashes, login | Suggest first-line troubleshooting (clear cache, restart); ask for one diagnostic detail |
| `general_agent` | Feedback, praise, misc | Warm acknowledgement; if the topic is not in documentation (for example stock ticker), say *"I don't know based on our documentation."* |
| `needs_clarification_agent` | Ambiguous cases | Asks one short question: billing, technical, or something else, without guessing |

Each agent increments `llm_calls` by 1.

#### `failure_handler` (U3-4)
Returns a safe message promising a human response within 24 hours, tagged with the internal error. Sets `category="general"`, clears escalation fields, and records the fallback in `thread_history`.

#### `escalation_check` (U4-3)
Sets `escalated=True` if **any** of these hold:

| Trigger | Reason string |
|---------|---------------|
| Anger keyword present (`_is_angry`) | "Anger keywords detected in complaint." |
| `category == "needs_clarification"` | "Complaint could not be reliably classified after multiple attempts." |
| `human_override` is set | "Selected for supervisory quality audit & human approval." |

Keywords: `furious, outraged, unacceptable, lawyer, sue, scam, fraud, disgusting, worst, terrible, useless, ridiculous`.

#### `human_review` (U4-3)
Prints the reason, customer, complaint and draft. The decision comes from, in priority order:

1. `human_override` (scripted demos)
2. `--auto-approve` flag: `REJECT: …` if the reason contains "Anger", otherwise `APPROVE`
3. Interactive `input()` from the terminal

`APPROVE` keeps the draft. Anything else replaces the reply with a standard senior-team escalation message (specialist contact within 4 business hours) and includes the reviewer's reason as an internal note.

### 4.4 Routing functions

| Function | Returns |
|----------|---------|
| `route_by_category` | `failure_handler` for `__tool_error__`; otherwise the matching specialist; unknown categories fall through to `general_agent` |
| `route_after_escalation` | `human_review` if `escalated`, else `END` |

### 4.5 Building and running

`build_graph(checkpointer=None)` wires the nodes and edges and compiles the graph. The demo creates two apps:

- `app_with_ckpt`: compiled with `SqliteSaver` (`checkpoints.db`)
- `app_no_ckpt`: compiled without a checkpointer, used to show "amnesia"

`run_case(...)` initialises state via `_init_state`, picks a `thread_id` (explicit config or `conversation_id`), invokes the graph, prints metrics, and persists resolved complaints through `store_complaint`.

### 4.6 CLI

| Flag | Effect |
|------|--------|
| *(none)* | Interactive: `human_review` waits on stdin |
| `--auto-approve` | Non-interactive decision injection for trace capture |

---

## 5. Data stores

### 5.1 `complaints.db` (long-term memory)

Created and managed by `seed_db.py`.

**`complaints`**

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK AUTOINCREMENT | |
| `customer_id` | TEXT | |
| `conversation_id` | TEXT | |
| `timestamp` | TEXT | Defaults to `datetime('now')` |
| `complaint` | TEXT | |
| `category` | TEXT | |
| `response` | TEXT | |

**`profiles`** (namespace `"profile"`)

| Column | Type | Notes |
|--------|------|-------|
| `customer_id` | TEXT PK | |
| `namespace` | TEXT | Default `'profile'` |
| `preferred_channel` | TEXT | |
| `complaint_count` | INTEGER | Incremented on each stored complaint |
| `last_category` | TEXT | |
| `notes` | TEXT | |

**Seed data**

| Customer | Channel | Prior complaints | Notes |
|----------|---------|------------------|-------|
| `CUST001` | email | 2 billing | Repeat billing issue; refund issued |
| `CUST002` | chat | 1 technical | Android crash resolved after reinstall |
| `CUST003` | email | 0 | New customer |

**Helper API**

| Function | Purpose |
|----------|---------|
| `init_db()` | Create tables if missing |
| `seed_data()` | `INSERT OR IGNORE` sample rows |
| `store_complaint(...)` | Insert a complaint and upsert the profile counter and last category |
| `load_customer_history(id, limit=3)` | Formatted last-N complaints, oldest first; empty string if none |
| `load_profile(id)` | Profile dict, or defaults for unknown customers |
| `reset_db()` | Drop both tables |

### 5.2 `checkpoints.db` (short-term memory)

Written by LangGraph's `SqliteSaver`. Each `thread_id` gets its own checkpoint history. Reusing the same `thread_id` across invocations restores prior state, including `thread_history`.

### 5.3 `chroma_db/` (vector index)

Persistent Chroma store, collection name `policy_faq`, built by `rag_setup.py`.

---

## 6. RAG corpus and retrieval

### 6.1 Corpus format (`ta2/corpus/policy_faq.txt`)

Chunks are separated by `---` lines. Each has a `CHUNK:` id, `TOPIC:` title and a body paragraph.

| # | Topic |
|---|-------|
| 1 | Duplicate charge refund policy (5–7 business days, report within 60 days) |
| 2 | Subscription cancellation (30 days notice) |
| 3 | App crash troubleshooting (clear cache, reinstall, Android 10+/iOS 14+) |
| 4 | Login issues and password reset (2FA, 5-attempt lockout, 30 minutes) |
| 5 | Premium feature activation (up to 24 hours) |
| 6 | Escalation policy (Tier-1 → Tier-2 → Manager) |
| 7 | SLA commitments |
| 8 | Contact information |
| 9 | Angry customer protocol (human must approve outgoing replies) |
| 10 | Data privacy and GDPR opt-out |

### 6.2 `rag_setup.py`

| Function | Description |
|----------|-------------|
| `load_chunks()` | Parses the corpus into LangChain `Document`s; metadata holds `chunk_id` and `topic` |
| `build_index()` | Deletes any existing `chroma_db/`, embeds all chunks with `nomic-embed-text`, and persists |
| `load_index()` | Opens the persisted store |
| `get_retriever(k)` | Returns a retriever with `search_kwargs={"k": k}` |
| `retrieve(query, k)` | Returns a formatted string: `[FAQ n — Topic]` followed by the chunk body |

Running the script directly rebuilds the index and performs a smoke test (`"duplicate charge refund"` at k=3 and k=1, then an unanswerable `"stock ticker symbol"` query).

### 6.3 Why k matters

- **k=1**: tight, low-noise context, but can miss a second relevant policy.
- **k=3**: broader coverage, but adds irrelevant text that a 3B model may latch onto.

The `rag_k1_vs_k3.txt` trace compares both on the same complaint.

---

## 7. Demo suites and traces

| Function | Section | Output file |
|----------|---------|-------------|
| `demo_main_cases` | 1: six main cases | `ta2_traces.txt` (full run) |
| `demo_short_term_memory` | 2: with vs without checkpointer | `memory_with.txt`, `memory_without.txt` |
| `demo_long_term_memory` | 3: restart demo for `CUST001` | `restart_demo.txt` |
| `demo_rag` | 4: k=1, k=3, unanswerable | `rag_k1_vs_k3.txt` |
| `demo_tool_failure` | 5: swaps `llm_sampling` for a `BrokenLLM` that raises `RuntimeError` | `tool_failure.txt` |
| `demo_oversight` | 6: approved and rejected HITL paths | `escalation_approved.txt`, `escalation_rejected.txt` |
| `format_challenge_table` | 7: metrics table | `challenge_analysis.txt` |

The six main cases are: billing (clean), technical (clean), general (clean), ambiguous (premium upgrade), ambiguous (account access), and angry (billing dispute with legal threat).

Traces for TA1 are in `traces/ta1_traces.txt`. `traces/challenge_analysis.txt` is produced from the six main cases.

### Typical metrics

| Case type | LLM calls | Hops | Notes |
|-----------|-----------|------|-------|
| Clean / ambiguous (non-angry) | 4 | 1 | 3 votes + 1 reply |
| Angry | 4 | 1 | Escalated to human review |
| Tool failure | 0 | 1 | Classification never completes |

---

## 8. Evaluation summary

From `report/report.md` (TA1 baseline vs TA2):

**Improved**
- **Policy grounding**: replies cite concrete policy facts (5–7 day refunds, 24-hour activation window, cache-clearing steps) rather than generic boilerplate.
- **Context persistence**: customers can ask follow-ups within a thread, and history carries across sessions.
- **Safety**: angry and ambiguous complaints reach a human with full context.

**Trade-offs**
- **Latency**: a TA2 ticket takes longer than TA1 (the report cites ~8–12 s vs ~3–5 s; the measured table shows 2–11 s depending on case and model warm-up).
- **Prompt size**: memory, thread history and RAG chunks add roughly 400–600 tokens per prompt, which is significant for a 3B model.

---

## 9. Extending the system

**Add a new category (for example `shipping`)**
1. Add it to `CLASSIFY_PROMPT` and to the allowed set in `_classify_once`.
2. Write a `shipping_agent` node using `_build_agent_prompt`.
3. Register it with `g.add_node`, add it to `route_by_category` and the conditional-edge map, and add an edge `shipping_agent → escalation_check`.
4. Add relevant chunks to `corpus/policy_faq.txt` and re-run `rag_setup.py`.

**Add policy knowledge**: append a `CHUNK / TOPIC / body` block separated by `---`, then run `python rag_setup.py`.

**Change the model**: edit the two `ChatOllama(model=...)` constructors. Larger models generally improve ambiguity handling and grounding.

**Tune escalation**: edit `ANGER_KEYWORDS`, or extend `escalation_check` with more rules (for example repeat-customer or high-value-account triggers).

**Use LangGraph's native interrupt for HITL**: replace the `input()` call in `human_review` with `interrupt()` and resume with a `Command`, so review can happen asynchronously (for example from a web UI).

---

## 10. Known limitations and observations

These come from reading the code and are listed to help future maintainers. They are not bugs that block normal use.

1. **Hop limit can't trigger in the current graph.** `classify_node` runs once per invocation and `hop_count` starts at 0, so `hop` is always 1 and `1 >= MAX_HOPS (3)` is never true. The guard only matters if a loop back to `classify` is added.
2. **Anger detection is whitespace-token based.** `_is_angry` splits on spaces, so `"unacceptable!"` or `"lawyer."` (with punctuation attached) won't match. Normalising punctuation or using regex word boundaries would make it more robust.
3. **`seed_db.py` is described as idempotent but resets data.** Its `__main__` block calls `reset_db()` first, so every run drops and recreates both tables, which erases any stored history.
4. **`rag_node` logs line count, not chunk count.** `len(ctx.splitlines())` counts text lines, so the printed `chunks_retrieved` number overstates the number of chunks.
5. **Human review uses `input()`**, not LangGraph's `interrupt()` (although the report's role table mentions `interrupt()`). This blocks the process and is unsuitable for a web service.
6. **Compound complaints.** The 3B model can vote unanimously for the first-mentioned intent (for example "payment failed or login bug" classified `billing 3:0`), so ambiguous complaints sometimes bypass clarification. Intent decomposition is the suggested fix.
7. **Generated artefacts are committed.** `checkpoints.db` (~7 MB), `complaints.db` and `chroma_db/` are in the repo. Consider adding them to `.gitignore` and regenerating locally.
8. **`wall_start` is stored but unused.** Elapsed time is measured separately in `run_case`.
9. **Fallback leaks internal error text.** `failure_handler` appends the exception message to the customer-facing response. For production, log it instead.
10. **Global monkey-patch in the failure demo.** `demo_tool_failure` replaces the module-level `llm_sampling`; it is restored in a `finally` block, but this pattern isn't thread-safe.

---

## 11. Glossary

| Term | Meaning |
|------|---------|
| **LangGraph** | Library for building stateful, graph-structured LLM workflows |
| **Checkpointer** | LangGraph component that persists graph state per `thread_id` |
| **Self-consistency** | Sampling the same prompt several times and aggregating the answers |
| **RAG** | Retrieval-Augmented Generation: injecting retrieved documents into the prompt |
| **HITL** | Human-in-the-loop: a person reviews or approves an automated output |
| **Hop** | One pass through the classify/supervisor step |
| **Reducer** | A function (here `operator.add`) that tells LangGraph how to merge node outputs into state |
| **Ollama** | Local runtime for serving open-weight LLMs |
