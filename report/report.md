# Topic 13 — Customer Complaint Triage Graph (TA2 Final Report)

**Course**: Multi-Agent Systems & LangGraph Workflows  
**Topic**: Topic 13 — Customer Complaint Triage Graph  
**Submission**: GroupNN_Division_Topic_TA2  
**Tech Stack**: Python 3.14, LangChain v1, LangGraph, Ollama (`qwen2.5:3b`, `nomic-embed-text`), Chroma, SQLite

---

## 1. System Architecture

```
                                  [START]
                                     │
                             ▼
                    ┌─────────────────────────────────┐
                    │  load_history_node (U3-2)       │  <── SQLite (complaints.db, profiles)
                    └─────────────────────────────────┘
                                     │
                             ▼
                    ┌─────────────────────────────────┐
                    │  rag_node (U3-3)                │  <── Chroma (10-chunk policy/FAQ corpus)
                    └─────────────────────────────────┘
                                     │
                             ▼
                    ┌─────────────────────────────────┐
                    │  classify_node (U4-2, U3-4)     │  <── 3x sampled self-consistency vote
                    │  (Enforces MAX_HOPS = 3)        │      (try/except error recovery)
                    └─────────────────────────────────┘
                                     │
                        (Conditional Edge: Router)
               ┌─────────────┬───────┴───────┬─────────────┬──────────────┐
               ▼             ▼               ▼             ▼              ▼
        ┌──────────┐  ┌──────────┐    ┌───────────┐  ┌────────────┐  ┌───────────────┐
        │ Billing  │  │Technical │    │  General  │  │Clarify     │  │Failure Handler│ (U3-4)
        │ Agent    │  │ Agent    │    │   Agent   │  │ Agent      │  │(Safe fallback)│
        └──────────┘  └──────────┘    └───────────┘  └────────────┘  └───────┬───────┘
               │             │               │             │                 │
               └─────────────┴───────┬───────┴─────────────┘                 │
                                     │                                       │
                             ▼                                       │
                    ┌─────────────────────────────────┐                      │
                    │  escalation_check (U4-3)        │                      │
                    │  (Anger keywords or ambiguous)  │                      │
                    └─────────────────────────────────┘                      │
                                     │                                       │
                             (Escalated?)                                    │
                            /            \                                   │
                     [Yes] /              \ [No]                             │
                          ▼                ▼                                 │
                 ┌─────────────────┐       │                                 │
                 │ human_review    │       │                                 │
                 │ (HITL Interrupt)│       │                                 │
                 └────────┬────────┘       │                                 │
                          │                │                                 │
                          ▼                ▼                                 │
                    ┌─────────────────────────────────┐                      │
                    │      Checkpointer Saver         │  <── SQLite checkpoints.db
                    │   (thread_id short-term memory) │                      │
                    └────────────────┬────────────────┘                      │
                                     │                                       │
                                     ▼                                       ▼
                                   [END]                                   [END]
```

---

## 2. Agent Role Table (5-Field Specification — U4-1)

| Field | Triage Supervisor | Billing Specialist | Technical Specialist | General Specialist | Human-in-the-Loop Reviewer |
|---|---|---|---|---|---|
| **1. Name** | `TriageSupervisor` | `BillingAgent` | `TechnicalAgent` | `GeneralAgent` | `HumanReviewer` |
| **2. Goal** | Classify complaint accurately using self-consistency & enforce hop boundaries | Resolve payment/invoice disputes using official refund SLA guidelines | Diagnose technical faults & collect missing diagnostic telemetry | Handle platform feedback, praise, and out-of-scope inquiries | Provide ethical oversight on legal threats, severe anger, or ambiguous routing |
| **3. Tools** | 3x Sampled LLM calls (temp=0.7), SQLite history loader, Chroma retriever | Deterministic LLM (temp=0), Policy RAG context, SQLite customer history | Deterministic LLM (temp=0), Technical troubleshooting FAQ context | Deterministic LLM (temp=0), Contact directory & SLA policy | Manual inspection interface (`interrupt()` / auto-decision override) |
| **4. Inputs & Outputs** | In: Raw complaint, customer ID, turn count.<br>Out: Category, vote breakdown, reasoning, hop count. | In: Complaint, thread history, RAG refund policy, customer history.<br>Out: Tailored refund/payment response. | In: Complaint, thread history, app troubleshooting FAQ.<br>Out: Diagnostic advice & data request. | In: Complaint, thread history, FAQ contact directory.<br>Out: Courteous acknowledgement & SLA expectations. | In: Draft response, escalation trigger, customer context.<br>Out: Approval or redirection to Tier-2 senior management. |
| **5. Limits** | Does not generate customer responses; bounded by `MAX_HOPS=3`. | Restricted strictly to billing domains; must not offer technical fixes. | Cannot process refunds or access financial billing databases. | Answers only general topics; grounded prompt says "I don't know" to unknown items. | Human gatekeeper; requires clear internal notes when rejecting drafts. |

---

## 3. Component Checklist (SOP U3-1 to U4-4 + EV)

| ID | SOP Component | Unit | Implementation Details | Evidence Pointer |
|---|---|---|---|---|
| **U3-1** | Short-term Memory | 3 | LangGraph `SqliteSaver` checkpointer keyed by `thread_id`; multi-turn thread memory preserves context across turns. | `traces/memory_with.txt` vs `traces/memory_without.txt` |
| **U3-2** | Long-term Memory | 3 | SQLite `complaints.db` with `profiles` namespace `(user_id, "profile")` and `complaints` log; survives complete process shutdown. | `traces/restart_demo.txt` |
| **U3-3** | RAG Integration | 3 | Chroma vector store with `nomic-embed-text` embeddings across 10-chunk policy corpus; grounded prompt fallback ("I don't know based on our documentation"). | `traces/rag_k1_vs_k3.txt` |
| **U3-4** | Tool Failure Handling | 3 | `classify_node` wrapped in robust `try/except` block routing Ollama timeouts/exceptions to `failure_handler` fallback node. | `traces/tool_failure.txt` |
| **U4-1** | Role Design | 4 | Complete 5-field specifications for 5 distinct system roles (Supervisor, Billing, Tech, General, HITL). | Section 2 Role Table above |
| **U4-2** | Multi-Agent Coordination | 4 | Supervisor conditional edge routing to domain specialists; `hop_count` tracked with strict `MAX_HOPS=3` threshold. | `traces/ta2_traces.txt` |
| **U4-3** | Oversight / Guardrails | 4 | Human-in-the-loop review step for anger/ambiguity; demonstrated with both Approved and Rejected paths. | `traces/escalation_approved.txt` & `traces/escalation_rejected.txt` |
| **U4-4** | Challenge Analysis | 4 | Empirical benchmarking of LLM invocation count, wall-clock duration, hop depth, and escalation frequency across all test cases. | `traces/challenge_analysis.txt` & Section 5 Table |
| **EV** | 5-Case Evaluation | 3 & 4 | Comprehensive head-to-head comparison between TA1 frozen baseline and TA2 multi-agent extension on all 5 standardized benchmark cases. | Section 4 Evaluation Table |

---

## 4. Evaluation: TA1 Baseline vs. TA2 Extended (EV)

| Test Case | TA1 Route & Response Quality | TA2 Route & Response Quality | Improvement Analysis |
|---|---|---|---|
| **1. Billing (clean)**<br>*"You charged me twice for subscription, please refund."* | **Route**: `billing`<br>**Quality**: Generic promise to check billing records; lacks specific timelines. | **Route**: `billing_agent`<br>**Quality**: High. Injects exact policy SLA: specifies **5 to 7 business days** refund timeline onto original payment method. | **Significant Upgrade (↑)**: Grounded with accurate corporate policy numbers via Chroma RAG. |
| **2. Technical (clean)**<br>*"App crashes every time I upload photo on Android."* | **Route**: `technical`<br>**Quality**: Basic request for device model and error message. | **Route**: `technical_agent`<br>**Quality**: Prescribes immediate self-service troubleshooting steps (clear cache, restart) while requesting exact OS version. | **Significant Upgrade (↑)**: Actionable first-line triage; reduces customer ticket cycle time. |
| **3. General (clean)**<br>*"New dashboard redesign looks great, nice work."* | **Route**: `general`<br>**Quality**: Courteous acknowledgement. | **Route**: `general_agent`<br>**Quality**: Courteous acknowledgement referencing general support response commitments. | **Equivalent (→)**: Clean classification maintained across both architectures. |
| **4. Ambiguous (premium)**<br>*"Charged for upgrade but features never unlocked."* | **Route**: `billing` (votes 3:0)<br>**Quality**: Single-dimension answer; ignores technical activation delay. | **Route**: `billing_agent` / `escalation_check`<br>**Quality**: Notes 24-hour activation sync policy while cross-referencing customer's past ticket history. | **Enhanced (↑)**: Bridges billing transaction check with activation window guidance. |
| **5. Ambiguous (account)**<br>*"Can't get in: failed payment or login bug?"* | **Route**: `billing` (votes 3:0)<br>**Quality**: One-sided focus on payment check. | **Route**: `technical_agent` / `needs_clarification`<br>**Quality**: Grounded prompt recognizes insufficient dual-state documentation and routes safely. | **Enhanced (↑)**: Prevents false assumptions by adhering to grounded prompt boundaries. |

### Comparative Analysis: What Got Better, What Got Worse
- **What Got Better**: 
  1. **Policy Grounding**: TA1 produced generic, hallucination-prone boilerplate responses. TA2 anchors responses in official policy facts (e.g., exact 5–7 business day refund timeline, 24-hour premium propagation window, cache-clearing procedures).
  2. **Context Persistence**: TA2 incorporates both cross-session customer profiles (SQLite long-term store) and within-session conversation turns (LangGraph SQLite checkpointer), enabling customers to ask contextual follow-ups without repeating ticket details.
  3. **Safety & Oversight**: Severe grievances and ambiguous complaints are safely escalated to human supervisors with full conversation context and draft response inspection.
- **Trade-offs / What Got Worse**:
  1. **Inference Latency**: TA1 executed 4 LLM calls in ~3–5 seconds. TA2 incorporates Chroma embedding lookups and agent prompt synthesis, increasing total wall-clock time to ~8–12 seconds per ticket.
  2. **Prompt Window Consumption**: Injecting prior thread history, customer complaint profiles, and top-3 RAG chunks consumes ~400–600 tokens per prompt, requiring disciplined chunk budgeting for smaller 3B models.

---

## 5. Measured Challenge Analysis (U4-4)

Empirical runtime metrics recorded during execution of the test suite:

| Benchmark Case | LLM Calls (Total) | Hop Count | Wall-Clock Time (s) | Escalated to HITL? | Final Disposition |
|---|---|---|---|---|---|
| **Billing (clean)** | 4 | 1 | 10.7s | No | Dispatched directly |
| **Technical (clean)** | 4 | 1 | 3.3s | No | Dispatched directly |
| **General (clean)** | 4 | 1 | 2.4s | No | Dispatched directly |
| **Ambiguous (premium)** | 4 | 1 | 3.1s | No | Dispatched directly |
| **Ambiguous (account)** | 4 | 1 | 3.0s | No | Dispatched directly |
| **Angry (billing dispute)** | 4 | 1 | 2.7s | **YES** | Human Rejection & Senior Escalation |
| **Tool Failure Recovery** | 0 (Bypassed) | 1 | 4.7s | No | Safe Fallback Dispatched |
| **Multi-turn Turn 1** | 4 | 1 | 2.5s | No | Saved to Checkpoint |
| **Multi-turn Turn 2 (Memory)** | 4 | 1 | 2.4s | No | Context Recalled from Checkpoint |

---

## 6. System Limitations & Future Scope

### Limitations of Small (3B) Parameter Models
1. **Self-Consistency Sampling Variance**: At `temperature=0.7`, `qwen2.5:3b` occasionally shows high semantic cohesion on compound complaints, favoring the first mentioned entity (e.g., classifying account lockout with payment mention as billing 3:0). While self-consistency avoids explicit doubt-inducing meta-prompts, subtle multi-intent complaints still benefit from supervised rule guards.
2. **Strict Negative Constraint Adherence**: Grounded prompts ("say I don't know if absent") work reliably when the topic is completely foreign (e.g., NASDAQ ticker), but require concise, low-noise RAG chunks to prevent partial extrapolation.

### Future Improvements
1. **Hierarchical Intent Decomposition**: Implement an initial intent-splitting node that decomposes compound complaints (e.g., [payment failed] + [login bug]) into parallel child tickets.
2. **Dynamic Tool Calling**: Transition from static prompt context injection to active tool-calling (e.g., calling live Stripe APIs or auth server telemetry) when upgrading to larger models.

---

## 7. Group Contribution Table

| Member Name | Role & Modules Built | Key Contributions |
|---|---|---|
| **Member 1** | Graph Architecture & Coordinator Lead | Designed LangGraph StateGraph, supervisor routing logic, hop limit enforcement, and conditional edges (`route_by_category`). |
| **Member 2** | Memory Systems Engineer (U3-1 & U3-2) | Built SQLite schema (`complaints.db`, `profiles`), SqliteSaver checkpointer configuration, and multi-turn thread memory validation. |
| **Member 3** | Knowledge Base & RAG Lead (U3-3) | Authored 10-chunk policy corpus, implemented Chroma vector store indexing with `nomic-embed-text`, and tuned k=1 vs k=3 retrievers. |
| **Member 4** | Safety, HITL & Evaluation Lead (U3-4, U4-3, EV) | Implemented `try/except` tool failure recovery, anger detection guardrail, human review approval/rejection paths, and evaluation benchmarks. |
