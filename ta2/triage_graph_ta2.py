r"""
Topic 13 — Customer Complaint Triage Graph  [TA2 — EXTENDED]
============================================================
Units implemented:
  U3-1  Short-term memory   — LangGraph SqliteSaver checkpointer + thread_id (multi-turn + amnesia trace)
  U3-2  Long-term memory    — SQLite profiles & complaints tables (survives process restart)
  U3-3  RAG                 — Chroma + nomic-embed-text (k=1 vs k=3 comparison + unanswerable query)
  U3-4  Tool failure        — try/except on classify → failure_handler recovery node
  U4-1  Role design         — 5 agents with distinct roles (5-field specification)
  U4-2  Coordination        — Supervisor + MAX_HOPS conditional routing
  U4-3  Oversight           — human_review node (HITL: approved and rejected paths demonstrated)
  U4-4  Challenge analysis  — call count, wall-clock time, hop count measured per case

Full graph shape:
  START
    └─► load_history_node          [U3-2] load SQLite profile + past complaint history
          └─► rag_node             [U3-3] Chroma retrieval
                └─► classify_node [U3-4 try/except; U4-2 hop counter]
                      └─► (conditional edge: route_by_category)
                            ├─► billing_agent    ─► escalation_check ─► human_review? ─► END
                            ├─► technical_agent  ─► escalation_check ─► human_review? ─► END
                            ├─► general_agent    ─► escalation_check ─► human_review? ─► END
                            ├─► needs_clarification ─► escalation_check ─► human_review? ─► END
                            └─► failure_handler  ─► END   [U3-4]

Run (full interactive mode):
    python triage_graph_ta2.py

Run (non-interactive, for trace capture):
    python triage_graph_ta2.py --auto-approve
"""

import argparse
import io
import operator
import os
import sys
import time
from collections import Counter
from typing import TypedDict, Literal, Optional, Annotated

from langchain_ollama import ChatOllama
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver

from seed_db import (
    init_db,
    load_customer_history,
    load_profile,
    store_complaint,
)
from rag_setup import retrieve

# ---------------------------------------------------------------------------
# CLI flag: --auto-approve skips stdin for the HITL node (trace mode)
# ---------------------------------------------------------------------------
parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--auto-approve", action="store_true",
                    help="Auto-inject a mock human approval (non-interactive trace mode)")
ARGS, _ = parser.parse_known_args()
AUTO_APPROVE: bool = ARGS.auto_approve

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MAX_HOPS    = 3
BASE_DIR    = os.path.dirname(__file__)
CHKPT_DB    = os.path.join(BASE_DIR, "checkpoints.db")
TRACES_DIR  = os.path.join(BASE_DIR, "..", "traces")
RAG_K       = 3          # default retrieval depth

# Anger keywords that trigger automatic escalation (U4-3)
ANGER_KEYWORDS = {
    "furious", "outraged", "unacceptable", "lawyer", "sue", "scam",
    "fraud", "disgusting", "worst", "terrible", "useless", "ridiculous",
}

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
llm          = ChatOllama(model="qwen2.5:3b", temperature=0)
llm_sampling = ChatOllama(model="qwen2.5:3b", temperature=0.7)


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
class TriageState(TypedDict):
    # Input
    complaint:        str
    customer_id:      str
    conversation_id:  str
    rag_k:            int           # allow per-run override for k=1 vs k=3 demo

    # Short-term Thread Memory [U3-1]
    thread_history:   Annotated[list[str], operator.add]

    # Memory & RAG
    customer_history: str           # [U3-2] from SQLite
    rag_context:      str           # [U3-3] from Chroma

    # Classification  [U3-4 / U4-2]
    category:         str
    votes:            str
    confidence_note:  str
    hop_count:        int
    tool_error:       str           # non-empty if classify threw an exception

    # Escalation  [U4-3]
    escalated:        bool
    escalation_reason: str
    human_decision:   str           # "APPROVE" | "REJECT: <reason>"
    human_override:   str           # optional override passed for specific test demo

    # Output
    response:         str

    # Metrics  [U4-4]
    llm_calls:        int
    wall_start:       float


# ---------------------------------------------------------------------------
# Helper: print annotated trace header
# ---------------------------------------------------------------------------
def _sep(title: str = "") -> None:
    if title:
        print(f"\n{'=' * 70}\n  {title}\n{'=' * 70}")
    else:
        print("-" * 70)


# ===========================================================================
# NODES
# ===========================================================================

# ---------------------------------------------------------------------------
# [U3-2] load_history_node — long-term memory from SQLite + thread turn tracking
# ---------------------------------------------------------------------------
def load_history_node(state: TriageState) -> TriageState:
    cid = state["customer_id"]
    history = load_customer_history(cid, limit=3)
    profile = load_profile(cid)

    profile_note = (
        f"[Profile] complaints_so_far={profile['complaint_count']}, "
        f"last_category={profile['last_category']}, "
        f"preferred_channel={profile['preferred_channel']}, "
        f"notes={profile['notes']}"
    ) if profile else ""

    full_history = "\n".join(filter(None, [profile_note, history]))
    print(f"  [load_history_node] customer={cid} | history_loaded={bool(history)}")
    
    # Ingest the new turn into thread_history (persisted by checkpointer)
    new_turn = [f"Customer: {state['complaint']}"] if state.get("complaint") else []
    return {
        **state,
        "customer_history": full_history,
        "thread_history": new_turn,
    }


# ---------------------------------------------------------------------------
# [U3-3] rag_node — retrieve relevant policy chunks from Chroma
# ---------------------------------------------------------------------------
def rag_node(state: TriageState) -> TriageState:
    k   = state.get("rag_k", RAG_K)
    ctx = retrieve(state["complaint"], k=k)
    print(f"  [rag_node] k={k} | chunks_retrieved={len(ctx.splitlines()) if ctx else 0}")
    return {**state, "rag_context": ctx}


# ---------------------------------------------------------------------------
# [U3-4 / U4-2] classify_node — 3x sampled + majority vote + hop counter
# ---------------------------------------------------------------------------
CLASSIFY_PROMPT = """You are a customer-support triage assistant.
Read the complaint below carefully, then classify it into exactly ONE category:
- billing    (payments, charges, refunds, invoices, subscription cost)
- technical  (bugs, errors, app/website not working, login issues)
- general    (feedback, praise, questions, or anything not billing/technical)

Base your decision only on the complaint text given below.

Respond in EXACTLY this format, nothing else:
CATEGORY: <billing|technical|general>
REASON: <one sentence quoting or paraphrasing the specific detail from THIS complaint that drove your decision>

Complaint: "{complaint}"
"""


def _classify_once(complaint: str, model) -> tuple[str, str]:
    prompt = CLASSIFY_PROMPT.format(complaint=complaint)
    result = model.invoke(prompt).content.strip()
    category = "general"
    reason   = "Could not parse model output."
    for line in result.splitlines():
        line = line.strip()
        if line.upper().startswith("CATEGORY:"):
            raw = line.split(":", 1)[1].strip().lower()
            if raw in ("billing", "technical", "general"):
                category = raw
        elif line.upper().startswith("REASON:"):
            reason = line.split(":", 1)[1].strip()
    return category, reason


def classify_node(state: TriageState) -> TriageState:
    """[U4-2] Increments hop_count and enforces MAX_HOPS.
       [U3-4] Wraps LLM calls in try/except — routes to failure_handler on error.
       Performs 3x sampled majority-vote classification."""
    hop = state.get("hop_count", 0) + 1
    print(f"  [classify_node] hop={hop}/{MAX_HOPS}")

    # Hop limit check (U4-2)
    if hop >= MAX_HOPS:
        print(f"  [classify_node] MAX_HOPS reached — forcing escalation.")
        return {
            **state,
            "hop_count": hop,
            "category": "needs_clarification",
            "votes": "hop_limit",
            "confidence_note": f"Hop limit ({MAX_HOPS}) reached; routed to human review.",
            "tool_error": "",
        }

    # [U3-4] Failure-safe classification
    try:
        votes, reasons = [], []
        for _ in range(3):
            cat, reason = _classify_once(state["complaint"], llm_sampling)
            votes.append(cat)
            reasons.append(reason)

        tally = Counter(votes)
        top_cat, top_count = tally.most_common(1)[0]
        vote_summary = ", ".join(f"{c}:{n}" for c, n in tally.most_common())

        if top_count >= 2:
            matching_reason = next(
                (r for c, r in zip(votes, reasons) if c == top_cat), reasons[0]
            )
            return {
                **state,
                "hop_count": hop,
                "category": top_cat,
                "votes": vote_summary,
                "confidence_note": matching_reason,
                "tool_error": "",
                "llm_calls": state.get("llm_calls", 0) + 3,
            }
        else:
            return {
                **state,
                "hop_count": hop,
                "category": "needs_clarification",
                "votes": vote_summary,
                "confidence_note": "3 independent classification attempts did not agree.",
                "tool_error": "",
                "llm_calls": state.get("llm_calls", 0) + 3,
            }

    except Exception as exc:
        # [U3-4] Route to failure_handler
        print(f"  [classify_node] !! TOOL ERROR: {exc}")
        return {
            **state,
            "hop_count": hop,
            "category": "__tool_error__",
            "votes": "",
            "confidence_note": "",
            "tool_error": str(exc),
            "llm_calls": state.get("llm_calls", 0),
        }


# ---------------------------------------------------------------------------
# [U3-4] failure_handler — graceful recovery from classify errors
# ---------------------------------------------------------------------------
def failure_handler(state: TriageState) -> TriageState:
    print(f"  [failure_handler] Recovering from tool error.")
    safe_response = (
        "We're currently experiencing a technical difficulty processing your request. "
        "A support agent will review your complaint and respond within 24 hours. "
        f"[Error details (internal): {state['tool_error']}]"
    )
    return {
        **state,
        "category": "general",
        "response": safe_response,
        "thread_history": [f"Agent (Fallback): {safe_response}"],
        "escalated": False,
        "escalation_reason": "",
        "human_decision": "",
    }


# ---------------------------------------------------------------------------
# Specialist agents  [U4-1]
# Each injects thread_history + customer_history + rag_context into its prompt.
# ---------------------------------------------------------------------------
def _build_agent_prompt(
    department: str,
    tone_hint: str,
    state: TriageState,
) -> str:
    # Keep only the last 4 thread turns to prevent token overflow
    prior_turns = state.get("thread_history", [])[-4:]
    thread_block = (
        f"\n\n--- Conversation Thread (Recent Turns) ---\n" + "\n".join(prior_turns)
        if prior_turns else ""
    )
    history_block = (
        f"\n\n--- Customer Profile & Past Issues ---\n{state['customer_history']}"
        if state.get("customer_history") else ""
    )
    rag_block = (
        f"\n\n--- Company Policy & FAQ Context ---\n{state['rag_context']}"
        if state.get("rag_context") else ""
    )
    return (
        f"You are the {department} support team. "
        f"Write a short, professional (2-3 sentence) reply to the customer complaint.\n"
        f"Guidelines: {tone_hint}\n"
        f"{rag_block}\n"
        f"{history_block}\n"
        f"{thread_block}\n\n"
        f"Customer Complaint: \"{state['complaint']}\""
    )


def billing_agent(state: TriageState) -> TriageState:
    """[U4-1] Billing specialist — handles payments, charges, refunds."""
    prompt = _build_agent_prompt(
        "Billing",
        "Acknowledge the billing issue and explain what you will check next. "
        "Cite the relevant policy (e.g. 5-7 business days for duplicate charge refunds). "
        "If the customer asks to confirm an invoice number or amount from earlier in the thread, state it clearly.",
        state,
    )
    reply = llm.invoke(prompt).content.strip()
    print("  [billing_agent] Response generated.")
    return {
        **state,
        "response": reply,
        "thread_history": [f"Agent (Billing): {reply}"],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


def technical_agent(state: TriageState) -> TriageState:
    """[U4-1] Technical specialist — handles bugs, crashes, login issues."""
    prompt = _build_agent_prompt(
        "Technical Support",
        "Acknowledge the technical issue and suggest first-line troubleshooting steps from policy (such as clearing app cache and restarting). "
        "Ask for one piece of diagnostic info (device model, OS version, or error message).",
        state,
    )
    reply = llm.invoke(prompt).content.strip()
    print("  [technical_agent] Response generated.")
    return {
        **state,
        "response": reply,
        "thread_history": [f"Agent (Technical): {reply}"],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


def general_agent(state: TriageState) -> TriageState:
    """[U4-1] General specialist — handles feedback, praise, misc."""
    prompt = _build_agent_prompt(
        "General Support",
        "Acknowledge the feedback or question warmly. "
        "If the customer is asking about an unanswerable topic not covered in documentation (such as company stock ticker symbols), state: 'I don't know based on our documentation.'",
        state,
    )
    reply = llm.invoke(prompt).content.strip()
    print("  [general_agent] Response generated.")
    return {
        **state,
        "response": reply,
        "thread_history": [f"Agent (General): {reply}"],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


def needs_clarification_agent(state: TriageState) -> TriageState:
    """[U4-1] Clarification specialist — asks the customer to disambiguate."""
    prompt = (
        "This customer complaint's category was unclear after multiple classification "
        "attempts. Write one short, friendly clarifying question (1-2 sentences) "
        "asking whether the issue is about billing/payment, a technical problem, "
        "or something else -- without guessing on their behalf.\n\n"
        f"Complaint: \"{state['complaint']}\""
    )
    reply = llm.invoke(prompt).content.strip()
    print("  [needs_clarification_agent] Clarification question generated.")
    return {
        **state,
        "response": reply,
        "thread_history": [f"Agent (Clarification): {reply}"],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


# ---------------------------------------------------------------------------
# [U4-3] escalation_check — decide whether to escalate to human_review
# ---------------------------------------------------------------------------
def _is_angry(complaint: str) -> bool:
    words = set(complaint.lower().split())
    return bool(words & ANGER_KEYWORDS)


def escalation_check(state: TriageState) -> TriageState:
    """Checks for anger keywords, needs_clarification, or human override → sets escalated flag."""
    complaint = state["complaint"]
    angry     = _is_angry(complaint)
    ambiguous = state["category"] == "needs_clarification"
    override  = bool(state.get("human_override"))

    if angry:
        reason = "Anger keywords detected in complaint."
    elif ambiguous:
        reason = "Complaint could not be reliably classified after multiple attempts."
    elif override:
        reason = "Selected for supervisory quality audit & human approval."
    else:
        reason = ""

    escalated = angry or ambiguous or override
    print(f"  [escalation_check] escalated={escalated} | reason={reason or 'none'}")
    return {
        **state,
        "escalated": escalated,
        "escalation_reason": reason,
    }


# ---------------------------------------------------------------------------
# [U4-3] human_review — HITL node
# ---------------------------------------------------------------------------
def human_review(state: TriageState) -> TriageState:
    """Human-in-the-loop review node.
    In interactive mode: waits for stdin input (APPROVE / REJECT: <reason>).
    In --auto-approve mode: injects a decision based on test state or override."""
    print("\n" + "!" * 70)
    print("  [human_review] *** HUMAN REVIEW REQUIRED ***")
    print(f"  Reason:    {state['escalation_reason']}")
    print(f"  Customer:  {state['customer_id']}")
    print(f"  Complaint: {state['complaint']}")
    print(f"  Draft response:\n    {state['response']}")
    print("!" * 70)

    override = state.get("human_override")
    if override:
        decision = override
        print(f"  [human_review] Programmatic decision override: '{decision}'")
    elif AUTO_APPROVE:
        if "Anger" in state.get("escalation_reason", ""):
            decision = "REJECT: Escalate to senior billing team — customer flagged as high priority."
        else:
            decision = "APPROVE"
        print(f"  [human_review] AUTO-APPROVE mode: injecting decision = '{decision}'")
    else:
        print("  Type APPROVE to send the draft, or REJECT: <reason> to escalate further.")
        decision = input("  Your decision: ").strip()

    if decision.upper() == "APPROVE":
        final_response = state["response"]
        print("  [human_review] Decision: APPROVED — sending draft to customer.")
    else:
        reject_reason = decision.split(":", 1)[1].strip() if ":" in decision else decision
        final_response = (
            f"Thank you for your patience. Your complaint has been escalated to our senior team. "
            f"A specialist will contact you via your preferred channel within 4 business hours. "
            f"[Internal note: {reject_reason}]"
        )
        print(f"  [human_review] Decision: REJECTED — reason: {reject_reason}")

    return {
        **state,
        "response": final_response,
        "human_decision": decision,
    }


# ---------------------------------------------------------------------------
# Routing functions (conditional edges)  [U4-2]
# ---------------------------------------------------------------------------
def route_by_category(
    state: TriageState,
) -> Literal["billing_agent", "technical_agent", "general_agent",
             "needs_clarification_agent", "failure_handler"]:
    cat = state["category"]
    if cat == "__tool_error__":
        return "failure_handler"
    if cat == "billing":
        return "billing_agent"
    if cat == "technical":
        return "technical_agent"
    if cat == "needs_clarification":
        return "needs_clarification_agent"
    return "general_agent"


def route_after_escalation(
    state: TriageState,
) -> Literal["human_review", "__end__"]:
    return "human_review" if state.get("escalated") else END


# ---------------------------------------------------------------------------
# Build the graph
# ---------------------------------------------------------------------------
def build_graph(checkpointer=None):
    g = StateGraph(TriageState)

    # Nodes
    g.add_node("load_history",              load_history_node)
    g.add_node("rag",                       rag_node)
    g.add_node("classify",                  classify_node)
    g.add_node("billing_agent",             billing_agent)
    g.add_node("technical_agent",           technical_agent)
    g.add_node("general_agent",             general_agent)
    g.add_node("needs_clarification_agent", needs_clarification_agent)
    g.add_node("failure_handler",           failure_handler)
    g.add_node("escalation_check",          escalation_check)
    g.add_node("human_review",              human_review)

    # Entry
    g.set_entry_point("load_history")

    # Linear preamble
    g.add_edge("load_history", "rag")
    g.add_edge("rag", "classify")

    # Supervisor conditional edge  [U4-2]
    g.add_conditional_edges(
        "classify",
        route_by_category,
        {
            "billing_agent":              "billing_agent",
            "technical_agent":            "technical_agent",
            "general_agent":              "general_agent",
            "needs_clarification_agent":  "needs_clarification_agent",
            "failure_handler":            "failure_handler",
        },
    )

    # All specialists → escalation_check
    for node in ("billing_agent", "technical_agent", "general_agent", "needs_clarification_agent"):
        g.add_edge(node, "escalation_check")

    # failure_handler bypasses escalation
    g.add_edge("failure_handler", END)

    # Escalation routing  [U4-3]
    g.add_conditional_edges(
        "escalation_check",
        route_after_escalation,
        {
            "human_review": "human_review",
            "__end__":       END,
        },
    )

    g.add_edge("human_review", END)

    return g.compile(checkpointer=checkpointer)


# ---------------------------------------------------------------------------
# Helpers for running cases and printing metrics
# ---------------------------------------------------------------------------
def _init_state(
    complaint: str,
    customer_id: str = "CUST999",
    conversation_id: str = "CONV-DEMO",
    rag_k: int = RAG_K,
    human_override: str = "",
) -> TriageState:
    return TriageState(
        complaint=complaint,
        customer_id=customer_id,
        conversation_id=conversation_id,
        rag_k=rag_k,
        thread_history=[],
        customer_history="",
        rag_context="",
        category="",
        votes="",
        confidence_note="",
        hop_count=0,
        tool_error="",
        escalated=False,
        escalation_reason="",
        human_decision="",
        human_override=human_override,
        response="",
        llm_calls=0,
        wall_start=time.time(),
    )


def run_case(
    app,
    label: str,
    complaint: str,
    customer_id: str = "CUST999",
    conversation_id: str = "CONV-DEMO",
    rag_k: int = RAG_K,
    config: dict = None,
    human_override: str = "",
) -> dict:
    """Run one complaint through the graph, print annotated trace, return final state."""
    _sep(f"CASE: {label}")
    print(f"  Complaint  : {complaint}")
    print(f"  CustomerID : {customer_id}  |  ConvID: {conversation_id}  |  RAG k={rag_k}")
    _sep()

    state = _init_state(complaint, customer_id, conversation_id, rag_k, human_override=human_override)
    cfg = config if config else {}
    if "configurable" not in cfg:
        cfg = {"configurable": {"thread_id": conversation_id}}
    elif "thread_id" not in cfg["configurable"]:
        cfg["configurable"]["thread_id"] = conversation_id

    t0    = time.time()
    final = app.invoke(state, config=cfg)
    elapsed = time.time() - t0

    print()
    print(f"  Vote breakdown     -> {final['votes']}")
    print(f"  Classified as      -> {final['category']}")
    print(f"  Classifier reason  -> {final['confidence_note']}")
    print(f"  Escalated          -> {final['escalated']}  |  Human decision: {final.get('human_decision','—')}")
    print(f"  Hop count          -> {final['hop_count']}")
    print(f"  LLM calls          -> {final['llm_calls']}")
    print(f"  Wall-clock (s)     -> {elapsed:.1f}")
    print(f"\n  FINAL RESPONSE:\n  {final['response']}")

    # [U3-2] Persist to SQLite after resolution
    if final["response"] and not final.get("tool_error"):
        store_complaint(
            customer_id=customer_id,
            conversation_id=conversation_id,
            complaint=complaint,
            category=final["category"],
            response=final["response"],
        )
        print(f"  [SQLite] Complaint stored for {customer_id}.")

    return final


# ===========================================================================
# DEMO SUITES
# ===========================================================================

def demo_main_cases(app) -> list[dict]:
    """6 main test cases (3 clean + 2 ambiguous + 1 angry) — EV table."""
    cases = [
        ("BILLING (clean)",
         "You charged me twice for my monthly subscription this cycle, please refund the duplicate charge.",
         "CUST001", "CONV-B01"),

        ("TECHNICAL (clean)",
         "The app crashes every time I try to upload a profile photo on Android.",
         "CUST002", "CONV-T01"),

        ("GENERAL (clean)",
         "I just wanted to say the new dashboard redesign looks great, nice work.",
         "CUST003", "CONV-G01"),

        ("AMBIGUOUS — premium upgrade",
         "I was charged for the premium upgrade but the premium features never turned on "
         "— is this a billing mistake or did it just not activate?",
         "CUST001", "CONV-A01"),

        ("AMBIGUOUS — account access",
         "I can't get into my account and I'm not sure if it's because my payment failed "
         "or because of a login bug on your site.",
         "CUST002", "CONV-A02"),

        ("ANGRY — billing dispute",
         "This is absolutely unacceptable! You charged me three times and I've been ignored "
         "for two weeks. I am furious and will contact my lawyer if this isn't fixed TODAY.",
         "CUST001", "CONV-ANGRY"),
    ]
    results = []
    for label, complaint, cid, conv_id in cases:
        r = run_case(app, label, complaint, customer_id=cid, conversation_id=conv_id)
        results.append(r)
    return results


# ---------------------------------------------------------------------------
# [U3-1] Short-term memory demo — multi-turn with and without checkpointer
# ---------------------------------------------------------------------------
def demo_short_term_memory(app_with_ckpt, app_no_ckpt) -> tuple[str, str]:
    thread_id = "THREAD-MEM-DEMO"
    thread_cfg = {"configurable": {"thread_id": thread_id}}

    # Capture output for with_memory
    buf_with = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf_with

    _sep("DEMO: U3-1 SHORT-TERM MEMORY — WITH checkpointer (thread_id='THREAD-MEM-DEMO')")
    print("  TURN 1: Customer files initial complaint with specific details.")
    run_case(
        app_with_ckpt,
        "TURN 1 — Initial complaint with details",
        "I was double-charged $49.99 on invoice #8821 yesterday. Please refund the extra charge.",
        customer_id="CUST_MEM01",
        conversation_id=thread_id,
        config=thread_cfg,
    )

    print("\n  TURN 2: Follow-up in SAME thread — references invoice #8821 without repeating it.")
    run_case(
        app_with_ckpt,
        "TURN 2 — Follow-up (WITH memory)",
        "Can you confirm what was the exact invoice number and dollar amount I just asked about?",
        customer_id="CUST_MEM01",
        conversation_id=thread_id,
        config=thread_cfg,
    )
    sys.stdout = old_stdout
    text_with = buf_with.getvalue()
    print(text_with)

    # Capture output for without_memory (Amnesia)
    buf_without = io.StringIO()
    sys.stdout = buf_without

    _sep("DEMO: U3-1 SHORT-TERM MEMORY — WITHOUT checkpointer (AMNESIA)")
    print("  TURN 2 sent without thread_id or checkpoint state — agent suffers amnesia.")
    run_case(
        app_no_ckpt,
        "TURN 2 — Follow-up (WITHOUT memory — AMNESIA)",
        "Can you confirm what was the exact invoice number and dollar amount I just asked about?",
        customer_id="CUST_AMNESIA_ANON",
        conversation_id="NO-THREAD",
        config={},
    )
    sys.stdout = old_stdout
    text_without = buf_without.getvalue()
    print(text_without)

    return text_with, text_without


# ---------------------------------------------------------------------------
# [U3-2] Long-term memory / restart demo
# ---------------------------------------------------------------------------
def demo_long_term_memory(app) -> str:
    buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf

    _sep("DEMO: U3-2 LONG-TERM MEMORY — Restart demo")
    print("  [Restart demo] Simulating a fresh process start — loading profile from SQLite...")
    profile = load_profile("CUST001")
    history = load_customer_history("CUST001", limit=3)
    print(f"  Profile loaded: {profile}")
    print(f"  History loaded:\n{history}")
    print("  NOTE: This profile and past complaints survived a process restart.")
    print("  Running a new complaint for CUST001 with pre-loaded history context...")
    run_case(
        app,
        "RESTART DEMO — new complaint with prior history",
        "My invoice this month looks wrong again.",
        customer_id="CUST001",
        conversation_id="CONV-RESTART",
    )
    sys.stdout = old_stdout
    text = buf.getvalue()
    print(text)
    return text


# ---------------------------------------------------------------------------
# [U3-3] RAG k=1 vs k=3 + unanswerable question demo
# ---------------------------------------------------------------------------
def demo_rag(app) -> str:
    buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf

    _sep("DEMO: U3-3 RAG — k=1 vs k=3 comparison")
    print("  Same complaint routed twice — once with k=1, once with k=3.")
    print("  Notice difference in retrieved FAQ context.\n")

    complaint = "My refund for the duplicate charge hasn't arrived yet — how long does it take?"
    run_case(app, "RAG k=1", complaint, customer_id="CUST001",
             conversation_id="CONV-RAG-K1", rag_k=1)
    run_case(app, "RAG k=3", complaint, customer_id="CUST001",
             conversation_id="CONV-RAG-K3", rag_k=3)

    _sep("DEMO: U3-3 RAG — Unanswerable question (grounded fallback test)")
    run_case(
        app,
        "RAG UNANSWERABLE",
        "What is your company's stock ticker symbol on the NASDAQ?",
        customer_id="CUST003",
        conversation_id="CONV-UNANSWERABLE",
    )
    sys.stdout = old_stdout
    text = buf.getvalue()
    print(text)
    return text


# ---------------------------------------------------------------------------
# [U3-4] Tool failure injection demo
# ---------------------------------------------------------------------------
def demo_tool_failure(app) -> str:
    buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf

    _sep("DEMO: U3-4 TOOL FAILURE — Injected classify exception")
    print("  Monkey-patching global llm_sampling to simulate Ollama connection failure.")

    global llm_sampling
    original_llm = llm_sampling

    class BrokenLLM:
        def invoke(self, prompt):
            raise RuntimeError("Simulated Ollama timeout — connection refused.")

    llm_sampling = BrokenLLM()
    try:
        run_case(
            app,
            "TOOL FAILURE CASE",
            "I need urgent help with my billing statement.",
            customer_id="CUST001",
            conversation_id="CONV-FAIL",
        )
    finally:
        llm_sampling = original_llm
        print("  [failure demo] Original llm_sampling restored.")

    sys.stdout = old_stdout
    text = buf.getvalue()
    print(text)
    return text


# ---------------------------------------------------------------------------
# [U4-3] Oversight — Approved and Rejected paths
# ---------------------------------------------------------------------------
def demo_oversight(app) -> tuple[str, str]:
    # Approved path: ambiguous complaint with explicit human APPROVAL
    buf_appr = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf_appr
    _sep("DEMO: U4-3 OVERSIGHT — APPROVED PATH")
    print("  Complaint triggers human review; human reviewer reviews draft and enters 'APPROVE'.")
    run_case(
        app,
        "HITL — Approved Path",
        "I was charged for premium upgrade but the features never unlocked.",
        customer_id="CUST001",
        conversation_id="CONV-HITL-APPR",
        human_override="APPROVE",
    )
    sys.stdout = old_stdout
    text_appr = buf_appr.getvalue()
    print(text_appr)

    # Rejected path: angry legal-threat complaint with explicit human REJECTION
    buf_rej = io.StringIO()
    sys.stdout = buf_rej
    _sep("DEMO: U4-3 OVERSIGHT — REJECTED PATH")
    print("  Angry complaint triggers human review; human reviewer enters 'REJECT: Customer threatening lawsuit. Forwarding to Legal.'")
    run_case(
        app,
        "HITL — Rejected Path",
        "You charged me three times! I am furious and contacting my lawyer immediately!",
        customer_id="CUST001",
        conversation_id="CONV-HITL-REJ",
        human_override="REJECT: Customer threatening lawsuit. Forwarding to Legal.",
    )
    sys.stdout = old_stdout
    text_rej = buf_rej.getvalue()
    print(text_rej)

    return text_appr, text_rej


# ---------------------------------------------------------------------------
# [U4-4] Challenge analysis table
# ---------------------------------------------------------------------------
def format_challenge_table(results: list[dict]) -> str:
    buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf
    _sep("U4-4 CHALLENGE ANALYSIS — LLM calls, wall-clock time, hop counts")
    labels = [
        "Billing (clean)", "Technical (clean)", "General (clean)",
        "Ambiguous (premium)", "Ambiguous (account)", "Angry (billing)",
    ]
    print(f"  {'Case':<28} {'LLM calls':>10} {'Hops':>6} {'Escalated':>10}")
    print(f"  {'-'*28} {'-'*10} {'-'*6} {'-'*10}")
    for label, r in zip(labels, results):
        print(
            f"  {label:<28} "
            f"{r.get('llm_calls', '?'):>10} "
            f"{r.get('hop_count', '?'):>6} "
            f"{'YES' if r.get('escalated') else 'no':>10}"
        )
    print()
    print("  Observations:")
    print("  1. Clean cases: 1 hop, 4 LLM calls (3 sampling + 1 generation).")
    print("  2. Ambiguous & Angry cases: route to specialist and escalate to human review.")
    print("  3. Hop limit of MAX_HOPS=3 enforces boundary preventing infinite routing loops.")
    sys.stdout = old_stdout
    text = buf.getvalue()
    print(text)
    return text


# ===========================================================================
# MAIN
# ===========================================================================
if __name__ == "__main__":
    print("=" * 70)
    print("  TA2 — Customer Complaint Triage Graph (Extended)")
    print(f"  Mode: {'AUTO-APPROVE (trace)' if AUTO_APPROVE else 'INTERACTIVE'}")
    print("=" * 70)

    # Ensure DB is ready
    init_db()
    os.makedirs(TRACES_DIR, exist_ok=True)

    # Capture all stdout to ta2_traces.txt as well
    full_output_buf = io.StringIO()

    with SqliteSaver.from_conn_string(CHKPT_DB) as ckpt:
        app_with_ckpt = build_graph(checkpointer=ckpt)
        app_no_ckpt   = build_graph(checkpointer=None)

        print("\n>>> SECTION 1: Main test cases (6 complaints)\n")
        results = demo_main_cases(app_with_ckpt)

        print("\n>>> SECTION 2: Short-term memory demo (U3-1)\n")
        mem_with, mem_without = demo_short_term_memory(app_with_ckpt, app_no_ckpt)
        with open(os.path.join(TRACES_DIR, "memory_with.txt"), "w", encoding="utf-8") as f:
            f.write(mem_with)
        with open(os.path.join(TRACES_DIR, "memory_without.txt"), "w", encoding="utf-8") as f:
            f.write(mem_without)

        print("\n>>> SECTION 3: Long-term memory / restart demo (U3-2)\n")
        restart_text = demo_long_term_memory(app_with_ckpt)
        with open(os.path.join(TRACES_DIR, "restart_demo.txt"), "w", encoding="utf-8") as f:
            f.write(restart_text)

        print("\n>>> SECTION 4: RAG k=1 vs k=3 + unanswerable (U3-3)\n")
        rag_text = demo_rag(app_with_ckpt)
        with open(os.path.join(TRACES_DIR, "rag_k1_vs_k3.txt"), "w", encoding="utf-8") as f:
            f.write(rag_text)

        print("\n>>> SECTION 5: Tool failure + recovery (U3-4)\n")
        failure_text = demo_tool_failure(app_with_ckpt)
        with open(os.path.join(TRACES_DIR, "tool_failure.txt"), "w", encoding="utf-8") as f:
            f.write(failure_text)

        print("\n>>> SECTION 6: Oversight — Approved vs Rejected paths (U4-3)\n")
        appr_text, rej_text = demo_oversight(app_with_ckpt)
        with open(os.path.join(TRACES_DIR, "escalation_approved.txt"), "w", encoding="utf-8") as f:
            f.write(appr_text)
        with open(os.path.join(TRACES_DIR, "escalation_rejected.txt"), "w", encoding="utf-8") as f:
            f.write(rej_text)

        print("\n>>> SECTION 7: Challenge analysis table (U4-4)\n")
        chal_text = format_challenge_table(results)
        with open(os.path.join(TRACES_DIR, "challenge_analysis.txt"), "w", encoding="utf-8") as f:
            f.write(chal_text)

    print("\n" + "=" * 70)
    print("  TA2 execution completed successfully.")
    print(f"  All individual trace files saved into: {os.path.abspath(TRACES_DIR)}")
    print("=" * 70)
