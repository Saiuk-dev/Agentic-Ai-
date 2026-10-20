"""
rag_setup.py — Build and persist a Chroma vector store from policy_faq.txt.

Uses nomic-embed-text (via Ollama) for embeddings.
The store is written to ./chroma_db (relative to this script).

Run:  python rag_setup.py
      (idempotent — rebuilds from scratch each time to keep corpus fresh)

Also exports:  get_retriever(k=3) -> a LangChain retriever ready for use.
"""

import os
import re
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings
from langchain_core.documents import Document

CORPUS_PATH  = os.path.join(os.path.dirname(__file__), "corpus", "policy_faq.txt")
CHROMA_DIR   = os.path.join(os.path.dirname(__file__), "chroma_db")
EMBED_MODEL  = "nomic-embed-text"
COLLECTION   = "policy_faq"


def load_chunks() -> list[Document]:
    """Parse policy_faq.txt into Document chunks, one per CHUNK: block."""
    with open(CORPUS_PATH, "r", encoding="utf-8") as f:
        raw = f.read()

    # Split on the --- separator between chunks
    blocks = [b.strip() for b in re.split(r"\n---\n", raw) if b.strip()]
    docs = []
    for block in blocks:
        lines = block.splitlines()
        chunk_id = ""
        topic    = ""
        body_lines = []
        for line in lines:
            if line.startswith("CHUNK:"):
                chunk_id = line.split(":", 1)[1].strip()
            elif line.startswith("TOPIC:"):
                topic = line.split(":", 1)[1].strip()
            else:
                body_lines.append(line)
        body = "\n".join(body_lines).strip()
        docs.append(Document(
            page_content=body,
            metadata={"chunk_id": chunk_id, "topic": topic},
        ))
    return docs


def build_index() -> Chroma:
    """Embed all chunks and write the Chroma vector store to disk."""
    docs = load_chunks()
    print(f"[rag_setup] Loaded {len(docs)} chunks from corpus.")

    embeddings = OllamaEmbeddings(model=EMBED_MODEL)

    # Delete existing collection if present so rebuild is clean
    if os.path.exists(CHROMA_DIR):
        import shutil
        shutil.rmtree(CHROMA_DIR)
        print(f"[rag_setup] Cleared old Chroma store at {CHROMA_DIR}")

    store = Chroma.from_documents(
        documents=docs,
        embedding=embeddings,
        collection_name=COLLECTION,
        persist_directory=CHROMA_DIR,
    )
    print(f"[rag_setup] Chroma index built and persisted to {CHROMA_DIR}")
    return store


def load_index() -> Chroma:
    """Load an already-built Chroma store from disk."""
    embeddings = OllamaEmbeddings(model=EMBED_MODEL)
    store = Chroma(
        collection_name=COLLECTION,
        embedding_function=embeddings,
        persist_directory=CHROMA_DIR,
    )
    return store


def get_retriever(k: int = 3):
    """Return a LangChain retriever from the persisted Chroma store.

    k controls how many chunks are retrieved per query.
    k=1 vs k=3 comparison is demonstrated in the main TA2 script.
    """
    store = load_index()
    return store.as_retriever(search_kwargs={"k": k})


def retrieve(query: str, k: int = 3) -> str:
    """Convenience: retrieve top-k chunks and return as a formatted string."""
    retriever = get_retriever(k=k)
    docs = retriever.invoke(query)
    if not docs:
        return ""
    parts = []
    for i, doc in enumerate(docs, 1):
        topic = doc.metadata.get("topic", "Unknown")
        parts.append(f"[FAQ {i} — {topic}]\n{doc.page_content}")
    return "\n\n".join(parts)


if __name__ == "__main__":
    build_index()

    # Quick smoke test — retrieve with k=3 and k=1
    print("\n[rag_setup] Smoke test — query: 'duplicate charge refund'")
    print("--- k=3 ---")
    print(retrieve("duplicate charge refund", k=3))
    print("\n--- k=1 ---")
    print(retrieve("duplicate charge refund", k=1))

    print("\n[rag_setup] Unanswerable query: 'stock ticker symbol'")
    print(retrieve("stock ticker symbol", k=3))
    print("[rag_setup] Done.")
