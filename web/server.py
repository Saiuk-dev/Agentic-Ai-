"""
server.py — FastAPI Web Backend for Topic 13: Customer Complaint Triage Graph (TA2)
Provides REST APIs for:
  - Interactive Triage & Live Graph Flow Streaming
  - Multi-Turn Thread Chat (U3-1 Memory vs Amnesia)
  - SQLite Customer Profiles & Complaint History (U3-2)
  - Chroma RAG Semantic Search & Policy Corpus (U3-3)
  - Tool Failure Injection & Recovery (U3-4)
  - Human-in-the-Loop Oversight (U4-3)
  - Real-time Analytics & Evaluation Dashboard (U4-4 & EV)
"""

import os
import sys
import time
import sqlite3
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

# Add ta2 directory to python path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TA2_DIR = os.path.join(BASE_DIR, "..", "ta2")
if TA2_DIR not in sys.path:
    sys.path.insert(0, TA2_DIR)

import triage_graph_ta2 as tg
from seed_db import (
    get_connection,
    init_db,
    reset_db,
    load_profile,
    load_customer_history,
    store_complaint,
)
from rag_setup import retrieve, get_retriever, CORPUS_PATH
from langgraph.checkpoint.sqlite import SqliteSaver

# Initialize FastAPI App
app = FastAPI(
    title="Customer Complaint Triage Graph — Multi-Agent Web UI",
    description="Interactive Web Interface for LangGraph Customer Support Triage System (Topic 13)",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Persistent checkpointer setup for thread-based multi-turn memory
CHKPT_FILE = os.path.join(TA2_DIR, "checkpoints.db")
ckpt_conn = sqlite3.connect(CHKPT_FILE, check_same_thread=False)
sqlite_checkpointer = SqliteSaver(ckpt_conn)

# Build cached graphs
app_with_memory = tg.build_graph(checkpointer=sqlite_checkpointer)
app_without_memory = tg.build_graph(checkpointer=None)

# Session metrics storage
session_metrics = {
    "total_processed": 0,
    "categories": {"billing": 0, "technical": 0, "general": 0, "needs_clarification": 0, "__tool_error__": 0},
    "escalated_count": 0,
    "total_wall_time": 0.0,
    "total_llm_calls": 0,
}


# ---------------------------------------------------------------------------
# Request & Response Schemas
# ---------------------------------------------------------------------------
class TriageRequest(BaseModel):
    complaint: str
    customer_id: str = "CUST001"
    conversation_id: str = "CONV-WEB"
    rag_k: int = 3
    use_checkpointer: bool = True
    human_action: str = "auto"  # "auto", "preview", "approve", "reject"
    human_override_text: Optional[str] = None
    simulate_failure: bool = False


class ChatTurnRequest(BaseModel):
    message: str
    customer_id: str = "CUST_MEM01"
    thread_id: str = "THREAD-LIVE-CHAT"
    use_checkpointer: bool = True


class RAGSearchRequest(BaseModel):
    query: str
    k: int = 3


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "topic": "Topic 13: Customer Complaint Triage Graph",
        "models": ["qwen2.5:3b", "nomic-embed-text"],
        "max_hops": tg.MAX_HOPS,
    }


@app.post("/api/triage")
def run_triage(req: TriageRequest):
    """
    Executes a complaint through the LangGraph workflow and returns:
    - Step-by-step node execution trace for the live graph visualizer
    - Category & vote breakdown
    - Escalation flag & reason
    - Grounded policy chunks retrieved
    - Customer history loaded from SQLite
    - Final response or draft response for HITL review
    """
    t_start = time.time()
    steps_log: List[Dict[str, Any]] = []

    # Handle Tool Failure Simulation (U3-4)
    original_llm = tg.llm_sampling
    if req.simulate_failure:
        class BrokenLLM:
            def invoke(self, prompt):
                raise RuntimeError("Simulated Ollama timeout — connection refused.")
        tg.llm_sampling = BrokenLLM()

    try:
        # Determine override if manual approval/rejection was passed
        override_val = ""
        if req.human_action == "approve":
            override_val = "APPROVE"
        elif req.human_action == "reject":
            reason = req.human_override_text or "Escalated to Tier-2 specialist by support supervisor."
            override_val = f"REJECT: {reason}"

        state = tg._init_state(
            complaint=req.complaint,
            customer_id=req.customer_id,
            conversation_id=req.conversation_id,
            rag_k=req.rag_k,
            human_override=override_val,
        )

        app_to_use = app_with_memory if req.use_checkpointer else app_without_memory
        cfg = {"configurable": {"thread_id": req.conversation_id}}

        # Step-by-step stream execution to record each node's behavior
        final_state = state.copy()
        
        # Track node timings
        node_t0 = time.time()
        for chunk in app_to_use.stream(state, config=cfg):
            node_name = list(chunk.keys())[0]
            node_state = chunk[node_name]
            node_elapsed = (time.time() - node_t0) * 1000.0
            node_t0 = time.time()

            # Merge into final state
            final_state.update(node_state)

            # Build metadata summary for this node
            step_info = {
                "node": node_name,
                "duration_ms": round(node_elapsed, 1),
                "timestamp": time.strftime("%H:%M:%S"),
            }

            if node_name == "load_history":
                step_info["summary"] = f"Checked SQLite for {req.customer_id}"
                step_info["details"] = {
                    "has_history": bool(node_state.get("customer_history")),
                    "history_preview": node_state.get("customer_history", "")[:180] + ("..." if len(node_state.get("customer_history", "")) > 180 else ""),
                }
            elif node_name == "rag":
                ctx = node_state.get("rag_context", "")
                chunks_count = len([c for c in ctx.split("\n\n") if c.strip()])
                step_info["summary"] = f"Retrieved top-{req.rag_k} FAQ policy chunks from Chroma"
                step_info["details"] = {
                    "chunks_found": chunks_count,
                    "rag_context": ctx,
                }
            elif node_name == "classify":
                step_info["summary"] = f"Supervisor 3x Vote: {node_state.get('votes', 'N/A')}"
                step_info["details"] = {
                    "category": node_state.get("category"),
                    "votes": node_state.get("votes"),
                    "confidence_note": node_state.get("confidence_note"),
                    "hop": node_state.get("hop_count"),
                    "tool_error": node_state.get("tool_error", ""),
                }
            elif node_name in ("billing_agent", "technical_agent", "general_agent", "needs_clarification_agent"):
                step_info["summary"] = f"{node_name} generated response"
                step_info["details"] = {
                    "draft_reply": node_state.get("response", ""),
                    "department": node_name.replace("_agent", "").capitalize(),
                }
            elif node_name == "failure_handler":
                step_info["summary"] = "Caught tool error — routed to safe fallback"
                step_info["details"] = {
                    "fallback_response": node_state.get("response", ""),
                    "error": node_state.get("tool_error", ""),
                }
            elif node_name == "escalation_check":
                step_info["summary"] = f"Escalation Flag: {node_state.get('escalated')}"
                step_info["details"] = {
                    "escalated": node_state.get("escalated"),
                    "reason": node_state.get("escalation_reason", "None"),
                }
            elif node_name == "human_review":
                step_info["summary"] = f"Human Oversight Decision: {node_state.get('human_decision')}"
                step_info["details"] = {
                    "decision": node_state.get("human_decision"),
                    "final_response": node_state.get("response"),
                }

            steps_log.append(step_info)

        total_elapsed = round(time.time() - t_start, 2)

        # Check if ticket triggered escalation and user asked for "preview"
        is_escalated = final_state.get("escalated", False)
        requires_review = is_escalated and req.human_action == "preview"

        # Update session metrics
        cat = final_state.get("category", "general")
        session_metrics["total_processed"] += 1
        session_metrics["categories"][cat] = session_metrics["categories"].get(cat, 0) + 1
        if is_escalated:
            session_metrics["escalated_count"] += 1
        session_metrics["total_wall_time"] += total_elapsed
        session_metrics["total_llm_calls"] += final_state.get("llm_calls", 4)

        # Store to SQLite if resolved and not previewing
        if not requires_review and final_state.get("response") and not final_state.get("tool_error"):
            store_complaint(
                customer_id=req.customer_id,
                conversation_id=req.conversation_id,
                complaint=req.complaint,
                category=final_state.get("category", "general"),
                response=final_state.get("response", ""),
            )

        return {
            "success": True,
            "category": final_state.get("category"),
            "votes": final_state.get("votes"),
            "confidence_note": final_state.get("confidence_note"),
            "response": final_state.get("response"),
            "draft_response": final_state.get("response") if is_escalated else "",
            "escalated": is_escalated,
            "escalation_reason": final_state.get("escalation_reason", ""),
            "human_decision": final_state.get("human_decision", ""),
            "requires_human_approval": requires_review,
            "hop_count": final_state.get("hop_count", 1),
            "llm_calls": final_state.get("llm_calls", 4),
            "wall_clock_s": total_elapsed,
            "tool_error": final_state.get("tool_error", ""),
            "steps": steps_log,
            "customer_history": final_state.get("customer_history", ""),
            "rag_context": final_state.get("rag_context", ""),
        }

    finally:
        if req.simulate_failure:
            tg.llm_sampling = original_llm


@app.post("/api/chat")
def chat_turn(req: ChatTurnRequest):
    """
    Multi-Turn Chat endpoint to demonstrate U3-1 short-term thread memory and Amnesia.
    """
    app_to_use = app_with_memory if req.use_checkpointer else app_without_memory
    cfg = {"configurable": {"thread_id": req.thread_id}}

    state = tg._init_state(
        complaint=req.message,
        customer_id=req.customer_id,
        conversation_id=req.thread_id,
        rag_k=3,
    )

    t0 = time.time()
    final = app_to_use.invoke(state, config=cfg)
    elapsed = round(time.time() - t0, 2)

    return {
        "reply": final.get("response", ""),
        "category": final.get("category", "general"),
        "thread_history": final.get("thread_history", []),
        "wall_clock_s": elapsed,
        "used_checkpointer": req.use_checkpointer,
    }


@app.get("/api/profiles")
def get_profiles_and_complaints():
    """Returns SQLite profiles and past complaints log."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT customer_id, namespace, preferred_channel, complaint_count, last_category, notes FROM profiles")
    profiles = [dict(row) for row in cur.fetchall()]

    cur.execute("SELECT id, customer_id, conversation_id, timestamp, complaint, category, response FROM complaints ORDER BY id DESC LIMIT 25")
    complaints = [dict(row) for row in cur.fetchall()]
    conn.close()

    return {
        "profiles": profiles,
        "recent_complaints": complaints,
    }


@app.post("/api/reset-db")
def reset_database():
    """Resets SQLite tables to pristine seed data."""
    reset_db()
    init_db()
    from seed_db import seed_data
    seed_data()
    return {"success": True, "message": "SQLite complaints.db restored to clean initial seed!"}


@app.post("/api/rag/search")
def search_rag(req: RAGSearchRequest):
    """Performs semantic search across Chroma policy index."""
    retriever = get_retriever(k=req.k)
    docs = retriever.invoke(req.query)
    results = []
    for doc in docs:
        results.append({
            "content": doc.page_content,
            "metadata": doc.metadata,
        })
    return {
        "query": req.query,
        "k": req.k,
        "results": results,
    }


@app.get("/api/rag/corpus")
def get_policy_corpus():
    """Reads all 10 chunks from corpus/policy_faq.txt."""
    if not os.path.exists(CORPUS_PATH):
        raise HTTPException(status_code=404, detail="Policy corpus file not found")
    with open(CORPUS_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    raw_chunks = content.split("\n---\n")
    chunks = []
    for i, c in enumerate(raw_chunks):
        c_str = c.strip()
        if c_str:
            lines = c_str.splitlines()
            topic = lines[0].replace("TOPIC:", "").strip() if lines and "TOPIC:" in lines[0] else f"FAQ Chunk {i+1}"
            chunks.append({
                "id": i + 1,
                "topic": topic,
                "text": c_str,
            })
    return {"chunks": chunks}


@app.get("/api/metrics")
def get_metrics():
    """Returns runtime metrics and challenge summary."""
    total = session_metrics["total_processed"]
    avg_time = round(session_metrics["total_wall_time"] / total, 2) if total > 0 else 0.0
    return {
        "session_metrics": session_metrics,
        "average_latency_s": avg_time,
        "max_hops": tg.MAX_HOPS,
    }


# ---------------------------------------------------------------------------
# Mount Static Files & Serve Frontend
# ---------------------------------------------------------------------------
STATIC_DIR = os.path.join(BASE_DIR, "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def serve_index():
    index_file = os.path.join(STATIC_DIR, "index.html")
    return FileResponse(index_file)


if __name__ == "__main__":
    import uvicorn
    print("\n" + "=" * 70)
    print("  CUSTOMER COMPLAINT TRIAGE GRAPH — INTERACTIVE WEB INTERFACE")
    print("  Running on: http://localhost:8000")
    print("=" * 70 + "\n")
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
