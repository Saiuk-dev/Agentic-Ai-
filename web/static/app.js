/**
 * app.js — Interactive Frontend Logic for Topic 13 (Customer Complaint Triage Graph)
 */

let currentRagK = 3;
let currentChatMemory = true;
let lastTriageResult = null;
let pendingHITLRequest = null;

// Preset Scenarios
const PRESETS = {
  billing: {
    label: "Clean Billing",
    complaint: "You charged me twice for my monthly subscription this cycle, please refund the duplicate charge.",
    customer_id: "CUST001",
    simulate_failure: false,
    badge: "Clean Billing (5-7d Refund SLA)"
  },
  technical: {
    label: "Clean Technical",
    complaint: "The app crashes every time I try to upload a profile photo on Android.",
    customer_id: "CUST002",
    simulate_failure: false,
    badge: "Clean Technical (Cache Troubleshooting)"
  },
  general: {
    label: "Clean General",
    complaint: "I just wanted to say the new dashboard redesign looks great, nice work.",
    customer_id: "CUST003",
    simulate_failure: false,
    badge: "Clean General (Customer Praise)"
  },
  ambig_premium: {
    label: "Ambiguous: Premium",
    complaint: "I was charged for the premium upgrade but the premium features never turned on — is this a billing mistake or did it just not activate?",
    customer_id: "CUST001",
    simulate_failure: false,
    badge: "Ambiguous (Dual Billing/Activation)"
  },
  ambig_access: {
    label: "Ambiguous: Access",
    complaint: "I can't get into my account and I'm not sure if it's because my payment failed or because of a login bug on your site.",
    customer_id: "CUST002",
    simulate_failure: false,
    badge: "Ambiguous (Login vs Payment)"
  },
  angry: {
    label: "Angry Dispute",
    complaint: "This is absolutely unacceptable! You charged me three times and I've been ignored for two weeks. I am furious and will contact my lawyer if this isn't fixed TODAY.",
    customer_id: "CUST001",
    simulate_failure: false,
    badge: "Angry Threat (Triggers HITL Guardrail)"
  },
  unanswerable: {
    label: "Unanswerable Query",
    complaint: "What is your company's stock ticker symbol on the NASDAQ?",
    customer_id: "CUST003",
    simulate_failure: false,
    badge: "Unanswerable Question (Grounded Fallback)"
  },
  tool_failure: {
    label: "Tool Failure",
    complaint: "I need urgent help with my billing statement.",
    customer_id: "CUST001",
    simulate_failure: true,
    badge: "Tool Failure Test (U3-4 Recovery Node)"
  }
};

// Customer Profiles metadata
const CUSTOMER_PROFILES = {
  CUST001: {
    channel: "email",
    notes: "Repeat billing issue; refund issued 2024-09. Flagged for priority care."
  },
  CUST002: {
    channel: "live-chat",
    notes: "Android beta tester; reported photo picker crash on Samsung Galaxy S23."
  },
  CUST003: {
    channel: "portal",
    notes: "Standard tier account. Frequent platform feedback contributor."
  },
  CUST_MEM01: {
    channel: "email",
    notes: "Short-term multi-turn memory verification profile."
  },
  CUST_AMNESIA_ANON: {
    channel: "anonymous",
    notes: "Unregistered test user (isolated from long-term SQLite context)."
  }
};

// Initialize on page load
document.addEventListener("DOMContentLoaded", () => {
  loadPreset("billing");
  setupHITLRadioListeners();
  refreshProfiles();
  loadAllCorpus();
  updateProfileCard("CUST001");

  document.getElementById("select-customer").addEventListener("change", (e) => {
    updateProfileCard(e.target.value);
  });
});

// Tab Switcher
function switchTab(tabName) {
  document.querySelectorAll(".tab-content").forEach((el) => el.classList.add("hidden"));
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.classList.remove("active", "bg-indigo-600", "text-white");
    btn.classList.add("text-slate-400");
  });

  const activeContent = document.getElementById(`tab-${tabName}`);
  const activeBtn = document.getElementById(`tab-btn-${tabName}`);

  if (activeContent) activeContent.classList.remove("hidden");
  if (activeBtn) {
    activeBtn.classList.add("active", "bg-indigo-600", "text-white");
    activeBtn.classList.remove("text-slate-400");
  }

  // Auto refresh specific tabs
  if (tabName === "memory") refreshProfiles();
  if (tabName === "rag") loadAllCorpus();
  lucide.createIcons();
}

// Preset Loader
function loadPreset(key) {
  const p = PRESETS[key];
  if (!p) return;

  document.getElementById("input-complaint").value = p.complaint;
  document.getElementById("select-customer").value = p.customer_id;
  document.getElementById("toggle-tool-failure").checked = p.simulate_failure;
  document.getElementById("scenario-badge").innerText = p.badge;

  updateProfileCard(p.customer_id);
}

function updateProfileCard(cid) {
  const meta = CUSTOMER_PROFILES[cid] || { channel: "email", notes: "Standard account." };
  document.getElementById("profile-card-cid").innerText = `${cid} Profile (SQLite)`;
  document.getElementById("profile-card-channel").innerText = `Channel: ${meta.channel}`;
  document.getElementById("profile-card-notes").innerText = meta.notes;
}

function setRagK(k) {
  currentRagK = k;
  const btn1 = document.getElementById("rag-k-1");
  const btn3 = document.getElementById("rag-k-3");
  if (k === 1) {
    btn1.className = "px-2 py-0.5 rounded text-[11px] bg-indigo-600 text-white font-bold";
    btn3.className = "px-2 py-0.5 rounded text-[11px] bg-slate-800 hover:bg-slate-700 text-slate-300";
  } else {
    btn3.className = "px-2 py-0.5 rounded text-[11px] bg-indigo-600 text-white font-bold";
    btn1.className = "px-2 py-0.5 rounded text-[11px] bg-slate-800 hover:bg-slate-700 text-slate-300";
  }
}

// ================= GRAPH ANIMATION & RESET =================
function resetGraphVisualizer() {
  const allNodes = [
    "node-start", "node-load_history", "node-rag", "node-classify",
    "node-billing_agent", "node-technical_agent", "node-general_agent",
    "node-needs_clarification_agent", "node-failure_handler",
    "node-escalation_check", "node-human_review", "node-end"
  ];
  allNodes.forEach((id) => {
    const el = document.getElementById(id);
    if (el) {
      el.className = "graph-node px-2.5 py-2 rounded-xl bg-slate-800/60 border border-slate-700/60 text-center transition-all";
      const meta = el.querySelector(".node-meta");
      if (meta && meta.getAttribute("data-default")) {
        meta.innerText = meta.getAttribute("data-default");
      }
    }
  });
}

function highlightNode(nodeId, type = "active", subtitle = "") {
  const el = document.getElementById(nodeId);
  if (!el) return;

  if (type === "active") {
    el.className = "graph-node px-2.5 py-2 rounded-xl bg-indigo-900/60 border-2 border-indigo-400 text-center shadow-lg shadow-indigo-500/20 node-active transition-all";
  } else if (type === "completed") {
    el.className = "graph-node px-2.5 py-2 rounded-xl bg-emerald-950/60 border border-emerald-500/80 text-center shadow-md shadow-emerald-500/10 transition-all";
  } else if (type === "escalated") {
    el.className = "graph-node px-2.5 py-2 rounded-xl bg-rose-950/70 border-2 border-rose-500 text-center shadow-lg shadow-rose-500/20 transition-all";
  } else if (type === "error") {
    el.className = "graph-node px-2.5 py-2 rounded-xl bg-red-950/70 border-2 border-red-500 text-center shadow-lg shadow-red-500/20 transition-all";
  }

  if (subtitle) {
    const meta = el.querySelector(".node-meta");
    if (meta) {
      if (!meta.getAttribute("data-default")) meta.setAttribute("data-default", meta.innerText);
      meta.innerText = subtitle;
    }
  }
}

// ================= LIVE TRIAGE EXECUTION =================
async function executeTriage(humanAction = null, humanOverride = null) {
  const complaint = document.getElementById("input-complaint").value.trim();
  if (!complaint) {
    alert("Please enter a customer complaint text.");
    return;
  }

  const customerId = document.getElementById("select-customer").value;
  const convId = document.getElementById("input-conv-id").value;
  const useCheckpointer = document.getElementById("toggle-checkpointer").checked;
  const hitlMode = document.getElementById("select-hitl-mode").value;
  const simulateFailure = document.getElementById("toggle-tool-failure").checked;

  const btn = document.getElementById("btn-run-triage");
  btn.disabled = true;
  btn.innerHTML = `<i data-lucide="loader-2" class="w-4 h-4 animate-spin"></i><span>Running LangGraph Workflow...</span>`;
  lucide.createIcons();

  resetGraphVisualizer();
  document.getElementById("flow-status").innerText = "Executing LangGraph nodes...";
  highlightNode("node-start", "completed");

  const payload = {
    complaint: complaint,
    customer_id: customerId,
    conversation_id: convId,
    rag_k: currentRagK,
    use_checkpointer: useCheckpointer,
    human_action: humanAction || hitlMode,
    human_override_text: humanOverride,
    simulate_failure: simulateFailure
  };

  try {
    const res = await fetch("/api/triage", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    lastTriageResult = data;

    // Animate execution steps
    if (data.steps && data.steps.length > 0) {
      for (const step of data.steps) {
        const domId = `node-${step.node}`;
        let statusType = "completed";
        if (step.node === "human_review" && data.escalated) statusType = "escalated";
        if (step.node === "failure_handler") statusType = "error";

        highlightNode(domId, statusType, `${step.duration_ms}ms`);
      }
    }
    highlightNode("node-end", "completed");

    // Check if human review is needed (Interactive Modal Mode)
    if (data.requires_human_approval) {
      pendingHITLRequest = payload;
      openHITLModal(data.escalation_reason, complaint, data.draft_response);
      document.getElementById("flow-status").innerText = "Paused at Human-in-the-Loop Gate";
      btn.disabled = false;
      btn.innerHTML = `<i data-lucide="play" class="w-4 h-4 fill-current"></i><span>Execute Triage Graph</span>`;
      lucide.createIcons();
      return;
    }

    // Render final output
    renderFinalResponse(data);
    document.getElementById("flow-status").innerText = `Completed in ${data.wall_clock_s}s`;

  } catch (err) {
    console.error(err);
    alert("Error executing triage: " + err.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<i data-lucide="play" class="w-4 h-4 fill-current"></i><span>Execute Triage Graph</span>`;
    lucide.createIcons();
  }
}

function renderFinalResponse(data) {
  const container = document.getElementById("response-container");
  container.className = "bg-slate-950 border border-slate-800 rounded-xl p-4 text-xs text-slate-100 leading-relaxed font-sans min-h-[90px] text-left block space-y-2";
  
  let escalationBadge = "";
  if (data.escalated) {
    escalationBadge = `<div class="mb-2 p-2 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-300 text-[11px] flex items-center justify-between">
      <span><b>HITL Oversight:</b> ${data.escalation_reason}</span>
      <span class="font-bold">${data.human_decision || "ESCALATED"}</span>
    </div>`;
  }

  container.innerHTML = `
    ${escalationBadge}
    <p class="text-xs leading-relaxed font-sans text-slate-100">${escapeHtml(data.response)}</p>
  `;

  // Update pills
  const pillCat = document.getElementById("pill-category");
  pillCat.innerText = data.category || "General";
  pillCat.className = `px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase ${
    data.category === "billing" ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30" :
    data.category === "technical" ? "bg-sky-500/20 text-sky-300 border border-sky-500/30" :
    data.category === "needs_clarification" ? "bg-amber-500/20 text-amber-300 border border-amber-500/30" :
    "bg-indigo-500/20 text-indigo-300 border border-indigo-500/30"
  }`;

  document.getElementById("pill-hops").innerText = `Hops: ${data.hop_count}`;
  document.getElementById("pill-time").innerText = `${data.wall_clock_s}s`;

  // Detail trace bar
  document.getElementById("trace-details").classList.remove("hidden");
  document.getElementById("trace-votes").innerText = data.votes || "1/1";
  document.getElementById("trace-calls").innerText = `${data.llm_calls} calls`;
  document.getElementById("trace-escalated").innerText = data.escalated ? "YES" : "No";
  document.getElementById("trace-reason").innerText = data.confidence_note || "Standard routing";
}

// ================= HITL MODAL =================
function setupHITLRadioListeners() {
  document.querySelectorAll('input[name="hitl-decision"]').forEach((radio) => {
    radio.addEventListener("change", (e) => {
      const rejectBox = document.getElementById("reject-note-box");
      if (e.target.value === "reject") {
        rejectBox.classList.remove("hidden");
      } else {
        rejectBox.classList.add("hidden");
      }
    });
  });
}

function openHITLModal(reason, complaint, draft) {
  document.getElementById("modal-escalation-reason").innerText = reason;
  document.getElementById("modal-complaint-text").innerText = `"${complaint}"`;
  document.getElementById("modal-draft-response").value = draft;
  document.getElementById("hitl-modal").classList.remove("hidden");
  lucide.createIcons();
}

function closeHITLModal() {
  document.getElementById("hitl-modal").classList.add("hidden");
}

async function submitHITLDecision() {
  const decision = document.querySelector('input[name="hitl-decision"]:checked').value;
  const rejectNote = document.getElementById("modal-reject-reason").value.trim();
  const draftText = document.getElementById("modal-draft-response").value.trim();

  closeHITLModal();

  if (decision === "approve") {
    await executeTriage("approve", draftText);
  } else {
    await executeTriage("reject", rejectNote);
  }
}

// ================= MULTI-TURN CHAT (U3-1) =================
let chatTurns = [];

function toggleChatMemory() {
  currentChatMemory = !currentChatMemory;
  const badge = document.getElementById("chat-memory-badge");
  if (currentChatMemory) {
    badge.className = "px-2.5 py-1 rounded-lg text-xs font-bold uppercase transition-all bg-emerald-600/20 text-emerald-400 border border-emerald-500/30";
    badge.innerText = "ACTIVE (WITH Memory)";
  } else {
    badge.className = "px-2.5 py-1 rounded-lg text-xs font-bold uppercase transition-all bg-rose-600/20 text-rose-400 border border-rose-500/30";
    badge.innerText = "OFF (Amnesia Demo)";
  }
}

function loadChatTurn1() {
  document.getElementById("chat-input").value = "I was double-charged $49.99 on invoice #8821 yesterday. Please refund the extra charge.";
}

function loadChatTurn2() {
  document.getElementById("chat-input").value = "Can you confirm what was the exact invoice number and dollar amount I just asked about?";
}

function clearChatThread() {
  chatTurns = [];
  document.getElementById("chat-messages").innerHTML = `<div class="text-center text-slate-500 italic my-8">Chat cleared. Start a new turn below.</div>`;
}

async function sendChatTurn(event) {
  event.preventDefault();
  const input = document.getElementById("chat-input");
  const msg = input.value.trim();
  if (!msg) return;

  input.value = "";
  const container = document.getElementById("chat-messages");
  if (chatTurns.length === 0) container.innerHTML = "";

  // Append user bubble
  const turnIdx = chatTurns.length + 1;
  container.innerHTML += `
    <div class="flex justify-end space-x-2">
      <div class="max-w-[75%] bg-indigo-600 text-white rounded-2xl rounded-tr-sm p-3 shadow-md">
        <div class="flex items-center justify-between text-[10px] text-indigo-200 mb-1">
          <span>Customer (Turn ${turnIdx})</span>
        </div>
        <p>${escapeHtml(msg)}</p>
      </div>
    </div>
  `;
  container.scrollTop = container.scrollHeight;

  // Bot loading placeholder
  const loadId = `bot-loading-${Date.now()}`;
  container.innerHTML += `
    <div id="${loadId}" class="flex justify-start space-x-2">
      <div class="max-w-[75%] bg-slate-900 border border-slate-800 text-slate-400 rounded-2xl rounded-tl-sm p-3">
        <span class="flex items-center space-x-2">
          <i data-lucide="loader" class="w-3.5 h-3.5 animate-spin text-indigo-400"></i>
          <span>Agent consulting LangGraph workflow...</span>
        </span>
      </div>
    </div>
  `;
  container.scrollTop = container.scrollHeight;
  lucide.createIcons();

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: msg,
        customer_id: "CUST_MEM01",
        thread_id: "THREAD-LIVE-CHAT",
        use_checkpointer: currentChatMemory
      })
    });
    const data = await res.json();
    document.getElementById(loadId).remove();

    // Append agent bubble
    const memTag = data.used_checkpointer
      ? `<span class="text-emerald-400 font-mono text-[9px] bg-emerald-500/10 px-1.5 py-0.5 rounded border border-emerald-500/20">Checkpointer Active</span>`
      : `<span class="text-rose-400 font-mono text-[9px] bg-rose-500/10 px-1.5 py-0.5 rounded border border-rose-500/20">Amnesia Mode (No Thread State)</span>`;

    container.innerHTML += `
      <div class="flex justify-start space-x-2">
        <div class="max-w-[75%] bg-slate-900 border border-slate-800 text-slate-200 rounded-2xl rounded-tl-sm p-3 shadow-md">
          <div class="flex items-center justify-between text-[10px] text-slate-400 mb-1 space-x-4">
            <span class="font-bold text-indigo-400">Agent (${data.category.toUpperCase()})</span>
            <div class="flex items-center space-x-1.5">
              ${memTag}
              <span class="font-mono text-slate-500">${data.wall_clock_s}s</span>
            </div>
          </div>
          <p class="leading-relaxed">${escapeHtml(data.reply)}</p>
        </div>
      </div>
    `;
    chatTurns.push({ user: msg, agent: data.reply });
    container.scrollTop = container.scrollHeight;

  } catch (err) {
    console.error(err);
    document.getElementById(loadId).innerHTML = `<span class="text-rose-400">Error: ${err.message}</span>`;
  }
}

// ================= SQLITE PROFILES & RESET (U3-2) =================
async function refreshProfiles() {
  try {
    const res = await fetch("/api/profiles");
    const data = await res.json();

    // Populate profiles
    const profBody = document.getElementById("table-profiles-body");
    if (data.profiles && data.profiles.length > 0) {
      profBody.innerHTML = data.profiles.map((p) => `
        <tr class="hover:bg-slate-800/40 transition-colors">
          <td class="p-3 font-mono font-bold text-indigo-300">${p.customer_id}</td>
          <td class="p-3 font-mono text-slate-400">${p.namespace}</td>
          <td class="p-3 font-medium text-emerald-400">${p.preferred_channel}</td>
          <td class="p-3 font-mono font-bold">${p.complaint_count}</td>
          <td class="p-3 font-mono text-slate-300 uppercase">${p.last_category || "—"}</td>
          <td class="p-3 text-slate-300">${escapeHtml(p.notes || "None")}</td>
        </tr>
      `).join("");
    } else {
      profBody.innerHTML = `<tr><td colspan="6" class="p-4 text-center text-slate-500">No profiles found in SQLite.</td></tr>`;
    }

    // Populate complaints log
    const compBody = document.getElementById("table-complaints-body");
    if (data.recent_complaints && data.recent_complaints.length > 0) {
      compBody.innerHTML = data.recent_complaints.map((c) => `
        <tr class="hover:bg-slate-800/40 transition-colors text-[11px]">
          <td class="p-2.5 font-mono text-slate-500">${c.id}</td>
          <td class="p-2.5 font-mono font-semibold text-indigo-300">${c.customer_id}</td>
          <td class="p-2.5 font-mono text-slate-400 whitespace-nowrap">${c.timestamp}</td>
          <td class="p-2.5 font-mono font-semibold uppercase text-emerald-400">${c.category}</td>
          <td class="p-2.5 text-slate-300 max-w-xs truncate" title="${escapeHtml(c.complaint)}">${escapeHtml(c.complaint)}</td>
          <td class="p-2.5 text-slate-300 max-w-xs truncate" title="${escapeHtml(c.response)}">${escapeHtml(c.response)}</td>
        </tr>
      `).join("");
    } else {
      compBody.innerHTML = `<tr><td colspan="6" class="p-4 text-center text-slate-500">No resolved complaints recorded yet.</td></tr>`;
    }

  } catch (err) {
    console.error(err);
  }
}

async function resetDatabaseUI() {
  if (!confirm("Are you sure you want to reset SQLite complaints.db to the pristine seed state?")) return;
  try {
    const res = await fetch("/api/reset-db", { method: "POST" });
    const data = await res.json();
    alert(data.message);
    refreshProfiles();
  } catch (err) {
    alert("Error resetting database: " + err.message);
  }
}

// ================= RAG CHROMA VECTOR SEARCH (U3-3) =================
function setRAGQuery(q) {
  document.getElementById("rag-search-input").value = q;
  testRAGSearch();
}

async function testRAGSearch() {
  const query = document.getElementById("rag-search-input").value.trim();
  if (!query) return;

  const container = document.getElementById("rag-results-list");
  container.innerHTML = `<div class="col-span-3 p-4 text-center text-sky-400 text-xs flex items-center justify-center space-x-2">
    <i data-lucide="loader" class="w-4 h-4 animate-spin"></i>
    <span>Searching Chroma vector embeddings...</span>
  </div>`;
  lucide.createIcons();

  try {
    const res = await fetch("/api/rag/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: query, k: 3 })
    });
    const data = await res.json();

    if (data.results && data.results.length > 0) {
      container.innerHTML = data.results.map((r, idx) => `
        <div class="bg-slate-950 p-3.5 rounded-xl border border-slate-800 space-y-2">
          <div class="flex items-center justify-between text-xs">
            <span class="font-bold text-sky-400">Match #${idx + 1}</span>
            <span class="font-mono text-[10px] text-slate-500">Chroma Distance</span>
          </div>
          <p class="text-[11px] text-slate-300 leading-relaxed font-sans">${escapeHtml(r.content)}</p>
        </div>
      `).join("");
    } else {
      container.innerHTML = `<div class="col-span-3 p-4 text-center text-slate-500 text-xs">No matching policy chunks found.</div>`;
    }
  } catch (err) {
    container.innerHTML = `<div class="col-span-3 p-4 text-center text-rose-400 text-xs">Error: ${err.message}</div>`;
  }
}

async function loadAllCorpus() {
  try {
    const res = await fetch("/api/rag/corpus");
    const data = await res.json();
    const list = document.getElementById("corpus-list");

    if (data.chunks && data.chunks.length > 0) {
      list.innerHTML = data.chunks.map((c) => `
        <div class="bg-slate-950/60 p-3 rounded-xl border border-slate-800/80 space-y-1">
          <div class="flex items-center justify-between text-[11px]">
            <span class="font-bold text-slate-200">Chunk #${c.id}: ${escapeHtml(c.topic)}</span>
          </div>
          <p class="text-[10px] text-slate-400 line-clamp-3">${escapeHtml(c.text)}</p>
        </div>
      `).join("");
    }
  } catch (err) {
    console.error(err);
  }
}

// Utility: escape HTML
function escapeHtml(str) {
  if (!str) return "";
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
