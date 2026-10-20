"""
generate_explainer_pdf.py — Generates a comprehensive, extreme-basics explainer PDF
for Topic 13: Customer Complaint Triage Graph (TA1 & TA2).
Zero code snippets — pure conceptual clarity, architecture breakdown, file directory guide,
and jury cheat sheet.
"""

import os
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, PageBreak, KeepTogether
)
from reportlab.pdfgen import canvas

PDF_PATH = os.path.join(os.path.dirname(__file__), "Topic13_Beginner_Explainer_Guide.pdf")


class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_header_footer(num_pages)
            super().showPage()
        super().save()

    def draw_header_footer(self, total_pages):
        self.saveState()
        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(colors.HexColor("#475569"))
        # Header (pages 2+)
        if self._pageNumber > 1:
            self.drawString(36, 756, "Topic 13: Customer Complaint Triage Graph — Plain English Explainer")
            self.setStrokeColor(colors.HexColor("#cbd5e1"))
            self.setLineWidth(0.5)
            self.line(36, 750, 576, 750)

        # Footer (all pages)
        self.setFont("Helvetica", 8)
        self.setStrokeColor(colors.HexColor("#cbd5e1"))
        self.setLineWidth(0.5)
        self.line(36, 36, 576, 36)
        self.drawString(36, 26, "Complete Concept & System Guide — Zero Code Snippets")
        self.drawRightString(576, 26, f"Page {self._pageNumber} of {total_pages}")
        self.restoreState()


def build_pdf():
    doc = SimpleDocTemplate(
        PDF_PATH,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=46,
        bottomMargin=46,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        textColor=colors.HexColor('#0f172a'),
        spaceAfter=3,
    )

    sub_style = ParagraphStyle(
        'DocSub',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#475569'),
        spaceAfter=12,
    )

    h1_style = ParagraphStyle(
        'H1',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        textColor=colors.HexColor('#1e3a8a'),
        spaceBefore=10,
        spaceAfter=4,
    )

    h2_style = ParagraphStyle(
        'H2',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=13,
        textColor=colors.HexColor('#1e293b'),
        spaceBefore=7,
        spaceAfter=3,
    )

    body_style = ParagraphStyle(
        'Body',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor('#1e293b'),
        spaceAfter=5,
    )

    bullet_style = ParagraphStyle(
        'Bullet',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor('#1e293b'),
        leftIndent=14,
        spaceAfter=3,
    )

    box_style = ParagraphStyle(
        'BoxText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=11.5,
        textColor=colors.HexColor('#0f172a'),
    )

    tbl_hdr = ParagraphStyle(
        'TblHdr',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        textColor=colors.white,
    )

    tbl_body = ParagraphStyle(
        'TblBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.8,
        leading=10.2,
        textColor=colors.HexColor('#0f172a'),
    )

    tbl_body_bold = ParagraphStyle(
        'TblBodyBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7.8,
        leading=10.2,
        textColor=colors.HexColor('#0f172a'),
    )

    story = []

    # ================= PAGE 1: THE BIG PICTURE & INTUITIVE ANALOGIES =================
    story.append(Paragraph("Customer Complaint Triage Graph: Beginner's Explainer", title_style))
    story.append(Paragraph(
        "<b>Topic 13</b> &nbsp;|&nbsp; <b>Multi-Agent LangGraph Workflow</b> &nbsp;|&nbsp; <b>Plain English Concept Guide</b>",
        sub_style
    ))

    story.append(Paragraph("1. The Real-World Problem: What Are We Trying to Solve?", h1_style))
    story.append(Paragraph(
        "Imagine running a massive online service. Every single minute, hundreds of customer complaints pour into your support inbox. "
        "Some customers were charged twice. Others have apps that keep crashing on Android. Some are sending praise, while others are "
        "furious and threatening legal action. If you hire hundreds of human agents to manually read, sort, and reply to every routine message, "
        "it costs millions and takes hours. If you use a single generic chatbot, it gets confused, makes false promises, and hallucinates.",
        body_style
    ))
    story.append(Paragraph(
        "<b>Our Goal:</b> Build an intelligent, automated digital support office. When a complaint arrives, the system instantly identifies "
        "who should handle it, checks the customer's past history, consults the company's official policy document, crafts an accurate reply, "
        "and immediately flags angry or dangerous complaints for human review.",
        body_style
    ))

    story.append(Paragraph("2. Extreme Basics: What is LangGraph, and Why 'Graph'?", h1_style))
    story.append(Paragraph(
        "Traditional programs run in a straight, rigid line: Step 1 → Step 2 → Step 3. But real customer conversations don't work like that. "
        "Depending on what the customer says, you might need to jump to Billing, or Technical, or ask a clarifying question, or stop everything "
        "and alert a human manager.",
        body_style
    ))
    story.append(Paragraph(
        "<b>LangGraph</b> is a framework that lets us build AI programs shaped like a <b>flowchart (a graph)</b>. It has three core building blocks:",
        body_style
    ))
    story.append(Paragraph("• <b>State (The Shared Clipboard):</b> A single dictionary or package of data that travels from worker to worker. It carries the customer's text, their history, the category, the policy facts, and the drafted reply.", bullet_style))
    story.append(Paragraph("• <b>Nodes (The Specialized Workers):</b> Each node is a focused function or agent designed to do exactly one job well (e.g., classify, look up policy, write a billing reply).", bullet_style))
    story.append(Paragraph("• <b>Edges (The Hallways and Doors):</b> The paths connecting the workers. A <i>conditional edge</i> is like a hallway with directional signs: it reads the clipboard and routes the ticket to the correct specialist door.", bullet_style))

    story.append(Paragraph("3. The Difference Between TA1 and TA2", h1_style))
    
    comp_data = [
        [
            Paragraph("System Dimension", tbl_hdr),
            Paragraph("TA1 (Baseline — What we started with)", tbl_hdr),
            Paragraph("TA2 (Extended — What we upgraded to)", tbl_hdr),
        ],
        [
            Paragraph("<b>Architecture</b>", tbl_body_bold),
            Paragraph("Single decision node with 3 basic reply branches.", tbl_body),
            Paragraph("Full Multi-Agent team with supervisor, memory, RAG, and human review.", tbl_body),
        ],
        [
            Paragraph("<b>Memory</b>", tbl_body_bold),
            Paragraph("Zero memory. Every complaint was treated as a stranger with no history.", tbl_body),
            Paragraph("<b>Two types of memory:</b> Short-term (chat turns) + Long-term (SQLite account history).", tbl_body),
        ],
        [
            Paragraph("<b>Company Policy</b>", tbl_body_bold),
            Paragraph("No policy access. Replies were generic AI guesses.", tbl_body),
            Paragraph("<b>RAG (Chroma DB):</b> Official policy FAQ retrieved and injected into answers.", tbl_body),
        ],
        [
            Paragraph("<b>Safety & Escalation</b>", tbl_body_bold),
            Paragraph("None. Angry threats received standard robotic replies.", tbl_body),
            Paragraph("<b>Human-in-the-Loop (HITL):</b> Anger and legal threats pause for human approval.", tbl_body),
        ],
        [
            Paragraph("<b>Reliability</b>", tbl_body_bold),
            Paragraph("If the AI failed or errored, the whole script crashed.", tbl_body),
            Paragraph("<b>Tool Failure Recovery:</b> Catches connection errors and sends safe fallback notes.", tbl_body),
        ],
    ]
    t_comp = Table(comp_data, colWidths=[100, 215, 225])
    t_comp.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a8a')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(t_comp)

    story.append(PageBreak())

    # ================= PAGE 2: THE 7 CORE BUILDING BLOCKS EXPLAINED =================
    story.append(Paragraph("4. The Core Concepts Explained Like You're 10 Years Old", h1_style))
    story.append(Paragraph(
        "Here is what each component actually does behind the scenes, using simple daily-life analogies:",
        body_style
    ))

    story.append(Paragraph("A. Short-Term Memory vs. Long-Term Memory (U3-1 & U3-2)", h2_style))
    story.append(Paragraph(
        "• <b>Short-Term Memory (The Active Phone Call Notepad):</b> When you call support, you tell the agent: <i>'I was double-charged $49.99 on invoice #8821.'</i> "
        "A minute later you ask: <i>'What was the invoice number I just gave you?'</i> If the agent has short-term memory (backed by <b>LangGraph SqliteSaver checkpointer</b>), "
        "they look at their notepad for this active call (keyed by <code>thread_id</code>) and answer: <i>'#8821'</i>. If you turn off the checkpointer, the agent suffers from "
        "<b>amnesia</b> and has no idea what you said five seconds ago.",
        body_style
    ))
    story.append(Paragraph(
        "• <b>Long-Term Memory (The Customer's Permanent File Folder):</b> When you hang up the phone, your notepad gets tossed, but the permanent record is saved to "
        "the company database (backed by <b>SQLite complaints.db</b>). Two months later when you call back from a different computer or after the server restarts, "
        "the agent looks up your Customer ID and sees: <i>'Ah, this customer has had 3 previous billing issues in September.'</i>",
        body_style
    ))

    story.append(Paragraph("B. RAG — Retrieval-Augmented Generation (U3-3)", h2_style))
    story.append(Paragraph(
        "• <b>The Open-Book Exam Analogy:</b> An AI model like <code>qwen2.5:3b</code> is like a student who knows general English, but knows <b>nothing</b> about your specific company. "
        "Instead of forcing the AI to guess how long a refund takes (which causes hallucinations), we give it an open book: <b>our 10-chunk policy document</b>.<br/>"
        "• <b>How Chroma and nomic-embed-text work:</b> We turn every policy paragraph into mathematical coordinates (embeddings). When a complaint mentions a duplicate charge, "
        "Chroma instantly pulls up Chunk #1 (which states: <i>'Duplicate charges are refunded within 5 to 7 business days'</i>) and hands it to the agent before it writes a single word.<br/>"
        "• <b>The Grounded Fallback:</b> What if a customer asks: <i>'What is your stock ticker symbol on the NASDAQ?'</i> The policy book doesn't say anything about stock tickers. "
        "Because our prompt is grounded, the agent refuses to make up a fake stock symbol and truthfully replies: <i>'I don't know based on our documentation.'</i>",
        body_style
    ))

    story.append(Paragraph("C. Self-Consistency Voting (Detecting Ambiguity Without Guessing)", h2_style))
    story.append(Paragraph(
        "Small 3B models struggle when you ask them: <i>'Are you sure you're right?'</i> (they get paranoid and doubt themselves). Instead, we use <b>majority voting</b>: "
        "we run the classification prompt 3 times at temperature=0.7 (slight randomness). If all 3 runs say <i>billing</i>, we are 100% confident. But if the runs split "
        "(e.g., 1 billing, 1 technical, 1 general), that disagreement itself is the proof that the complaint is ambiguous! No guessing required.",
        body_style
    ))

    story.append(Paragraph("D. The Supervisor & Hop Limit (U4-2)", h2_style))
    story.append(Paragraph(
        "The <b>Triage Supervisor</b> is the air-traffic controller. It never talks directly to the customer; it only inspects the clipboard and points the arrow to "
        "the right specialist agent. To protect the system, we enforce a <b>Hop Limit (MAX_HOPS = 3)</b>. If a ticket bounces between departments 3 times without resolution, "
        "the supervisor halts the cycle and escalates it to human review, preventing infinite loops and runaway server costs.",
        body_style
    ))

    story.append(Paragraph("E. Human-in-the-Loop Oversight (U4-3)", h2_style))
    story.append(Paragraph(
        "No company should let an autonomous bot reply to a customer who is screaming: <i>'I will sue you and contact my lawyer!'</i> "
        "Our system has an automated <b>anger and legal keyword detector</b>. When triggered, the system pauses execution using LangGraph's <code>interrupt()</code> mechanism. "
        "A human supervisor reviews the drafted reply and either enters <b>APPROVE</b> (sends it) or <b>REJECT</b> (intercepts it and assigns a human manager).",
        body_style
    ))

    story.append(Paragraph("F. Tool Failure Recovery (U3-4)", h2_style))
    story.append(Paragraph(
        "In production, AI servers (like Ollama) occasionally time out, run out of memory, or drop connections. Without failure handling, the whole application crashes with an ugly error. "
        "In TA2, the classifier is protected by a <code>try/except</code> shield. If Ollama crashes, the graph catches the error and routes to a safe <b>failure_handler</b> node that "
        "sends a polite reassurance to the customer that their ticket was saved and will be reviewed manually.",
        body_style
    ))

    story.append(PageBreak())

    # ================= PAGE 3: WHICH FILE DOES WHAT WORK? =================
    story.append(Paragraph("5. Complete Project File Directory: Which File Does What Work?", h1_style))
    story.append(Paragraph(
        "If the jury points to any file in your project and asks: <i>'What is the purpose of this file?'</i>, here is your exact reference:",
        body_style
    ))

    file_data = [
        [
            Paragraph("Folder / File Path", tbl_hdr),
            Paragraph("Purpose & What Work It Performs", tbl_hdr),
            Paragraph("Key Output / Role", tbl_hdr),
        ],
        [
            Paragraph("<b>ta1/<br/>triage_graph.py</b>", tbl_body_bold),
            Paragraph("The <b>frozen baseline code</b> from your original TA1 submission. Contains the single classifier node and three basic response nodes with no memory or RAG.", tbl_body),
            Paragraph("Baseline reference point for evaluation comparisons.", tbl_body),
        ],
        [
            Paragraph("<b>ta2/<br/>corpus/policy_faq.txt</b>", tbl_body_bold),
            Paragraph("The <b>company policy & FAQ document</b>. Contains 10 cleanly demarcated chunks covering refund timelines (5-7 days), app crash troubleshooting, login rules, and escalation SLAs.", tbl_body),
            Paragraph("The knowledge base that Chroma reads to answer customer questions.", tbl_body),
        ],
        [
            Paragraph("<b>ta2/<br/>seed_db.py</b>", tbl_body_bold),
            Paragraph("The <b>SQLite database builder</b>. Creates <code>complaints.db</code> with two tables: <code>profiles</code> (long-term customer data) and <code>complaints</code> (past ticket log). Contains <code>reset_db()</code> to restore clean test data.", tbl_body),
            Paragraph("Provides persistent memory that survives server reboots.", tbl_body),
        ],
        [
            Paragraph("<b>ta2/<br/>rag_setup.py</b>", tbl_body_bold),
            Paragraph("The <b>RAG vector database builder</b>. Reads <code>policy_faq.txt</code>, creates dense mathematical embeddings using <code>nomic-embed-text</code>, and stores them in <code>chroma_db/</code>.", tbl_body),
            Paragraph("Provides the <code>retrieve(query, k)</code> function used by agents.", tbl_body),
        ],
        [
            Paragraph("<b>ta2/<br/>triage_graph_ta2.py</b>", tbl_body_bold),
            Paragraph("<b>The heart of the entire project!</b> Defines the full LangGraph state machine, connects all nodes and conditional edges, implements checkpointer short-term memory, specialist agents, anger detection, and human review.", tbl_body),
            Paragraph("The main executable script that runs the entire multi-agent workflow.", tbl_body),
        ],
        [
            Paragraph("<b>ta2/<br/>requirements.txt</b>", tbl_body_bold),
            Paragraph("Lists all required Python libraries (LangGraph, LangChain, ChromaDB, SQLite checkpointer, Ollama integrations).", tbl_body),
            Paragraph("Ensures anyone can install the dependencies with one <code>pip</code> command.", tbl_body),
        ],
        [
            Paragraph("<b>ta2/<br/>README.md</b>", tbl_body_bold),
            Paragraph("User guide containing prerequisites, model pull commands, and the <b>one-command execution line</b> required by the SOP.", tbl_body),
            Paragraph("Instructions for running both automated and interactive modes.", tbl_body),
        ],
        [
            Paragraph("<b>report/<br/>report.pdf</b>", tbl_body_bold),
            Paragraph("The <b>official 4-page technical report</b> submitted to the jury. Contains the ASCII architecture diagram, 5-field agent role table, SOP checklist, TA1 vs TA2 evaluation, and challenge metrics.", tbl_body),
            Paragraph("Strictly budgeted to exactly 4 pages as mandated by the rubric.", tbl_body),
        ],
        [
            Paragraph("<b>report/<br/>generate_pdf.py</b>", tbl_body_bold),
            Paragraph("The ReportLab script that compiles <code>report.md</code> into the pixel-perfect 4-page PDF with custom running headers and footers.", tbl_body),
            Paragraph("Automated PDF compiler.", tbl_body),
        ],
        [
            Paragraph("<b>traces/<br/>*.txt (10 files)</b>", tbl_body_bold),
            Paragraph("Saved console outputs capturing evidence for every single grading item: TA1 baseline, TA2 full suite, memory with/without, restart demo, RAG k=1 vs k=3, tool failure recovery, HITL approved/rejected, and benchmark table.", tbl_body),
            Paragraph("Permanent proof for all jury criteria.", tbl_body),
        ],
    ]
    t_file = Table(file_data, colWidths=[110, 290, 140])
    t_file.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a8a')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(t_file)

    story.append(PageBreak())

    # ================= PAGE 4: STEP-BY-STEP COMPLAINT JOURNEY & JURY CHEAT SHEET =================
    story.append(Paragraph("6. Step-by-Step: The Journey of a Customer Complaint", h1_style))
    story.append(Paragraph(
        "When you run the script, what actually happens to a complaint second-by-second? Here is the exact path:",
        body_style
    ))

    journey_steps = [
        ("Step 1: Input Arrives", "The customer submits: 'You charged me twice for my subscription this month, refund me immediately!'"),
        ("Step 2: Check SQLite History", "The <code>load_history_node</code> checks SQLite for this customer ID. If they have past closed tickets, their profile is attached to the clipboard."),
        ("Step 3: Consult RAG FAQ", "The <code>rag_node</code> searches Chroma vector store and fetches Chunk #1: 'Duplicate charges are refunded within 5 to 7 business days'."),
        ("Step 4: Supervisor Classifies", "The <code>classify_node</code> runs 3 sampled votes at temperature=0.7. Result is 3:0 in favor of 'billing'. The hop counter increments to 1."),
        ("Step 5: Conditional Edge Routes", "The graph checks the category and sends the ticket to the <code>billing_agent</code> door."),
        ("Step 6: Specialist Writes Reply", "The <code>billing_agent</code> reads the customer complaint, their past history, and the 5-7 business day policy chunk, crafting an accurate, grounded reply."),
        ("Step 7: Safety & Anger Check", "The <code>escalation_check</code> scans the text. If no anger or legal threats are found, it bypasses human review. (If anger is found, it pauses for a human!)."),
        ("Step 8: Checkpointer Saves Turn", "The <code>SqliteSaver</code> checkpointer records the turn under <code>thread_id</code> so any follow-up question will remember this interaction."),
        ("Step 9: Finished & Stored", "The final reply is returned to the user and saved to the permanent SQLite complaints table for future reference."),
    ]

    for title, desc in journey_steps:
        story.append(Paragraph(f"• <b>{title}:</b> {desc}", bullet_style))

    story.append(Spacer(1, 6))

    story.append(Paragraph("7. Jury Defense Cheat Sheet: How to Answer Like a Pro", h1_style))

    jury_qa = [
        ("Jury Q1: Show me the exact routing logic that performs the routing.",
         "Answer: 'Our routing logic is implemented as a conditional edge in LangGraph called route_by_category(). It inspects the category field in the shared state. If the category is billing, it routes to billing_agent; if technical, to technical_agent; if needs_clarification, to the clarification agent; and if a tool exception occurred, to failure_handler. There is also a secondary conditional edge after the specialists that routes to human_review if the ticket was flagged as escalated.'"),

        ("Jury Q2: What would you add to handle ambiguous complaints more gracefully?",
         "Answer: 'Currently, when 3 sampled votes disagree, we route to needs_clarification_agent which asks a polite clarifying question. In production, we would add Parallel Multi-Intent Decomposition: when a customer has a compound complaint (like a failed payment combined with a website login crash), an intent-splitter node would split the ticket into two sub-tasks, run both Billing and Technical specialists in parallel, and merge their answers into one comprehensive response.'"),

        ("Jury Q3: How do you prove that memory actually works?",
         "Answer: 'We prove short-term memory through our amnesia test in traces/memory_with.txt versus traces/memory_without.txt. In Turn 1, the customer mentions invoice #8821 for $49.99. In Turn 2, they ask: what invoice did I just mention? With the checkpointer active, the agent recalls #8821. Without the checkpointer, the agent suffers amnesia and says it has no record of the invoice. For long-term memory, traces/restart_demo.txt proves that after killing the Python process, past complaints and customer profiles stored in SQLite are instantly reloaded.'"),

        ("Jury Q4: Why did you use majority voting instead of asking the model if it is confident?",
         "Answer: 'Small 3-billion parameter models like qwen2.5:3b suffer from meta-prompting bias. When you explicitly ask a small model are you sure you are right?, it tends to over-trigger and doubt itself even on obvious answers. By running self-consistency voting 3 times at temperature 0.7, disagreement between independent runs serves as the genuine mathematical signal for ambiguity.'"),
    ]

    for q, a in jury_qa:
        story.append(Paragraph(f"<b>{q}</b>", h2_style))
        story.append(Paragraph(f"{a}", body_style))

    # Build the document
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Beginner Explainer PDF built successfully: {PDF_PATH}")


if __name__ == "__main__":
    build_pdf()
