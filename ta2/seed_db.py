"""
seed_db.py — Initialise and seed the SQLite stores for TA2.

Creates two tables:
  complaints  — full complaint log (short-term history per customer)
  profiles    — long-term profile namespace (user_id, "profile")

Pre-populates 3 customers so the restart demo and history retrieval
work immediately without needing prior live runs.

Run:  python seed_db.py
      (idempotent — safe to run multiple times)
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "complaints.db")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables if they do not already exist."""
    conn = get_connection()
    cur = conn.cursor()

    # --- Complaint log (short-term / thread history) ---
    cur.execute("""
        CREATE TABLE IF NOT EXISTS complaints (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id     TEXT    NOT NULL,
            conversation_id TEXT    NOT NULL,
            timestamp       TEXT    NOT NULL DEFAULT (datetime('now')),
            complaint       TEXT    NOT NULL,
            category        TEXT    NOT NULL,
            response        TEXT    NOT NULL
        )
    """)

    # --- Long-term profile store (namespace = "profile") ---
    cur.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            customer_id       TEXT PRIMARY KEY,
            namespace         TEXT NOT NULL DEFAULT 'profile',
            preferred_channel TEXT,
            complaint_count   INTEGER NOT NULL DEFAULT 0,
            last_category     TEXT,
            notes             TEXT
        )
    """)

    conn.commit()
    conn.close()
    print("[seed_db] Tables initialised (or already exist).")


def seed_data() -> None:
    """Insert sample customers and past complaints.
    Uses INSERT OR IGNORE so re-running is safe."""
    conn = get_connection()
    cur = conn.cursor()

    # ---- Profiles ----
    profiles = [
        ("CUST001", "profile", "email",  2, "billing",   "Repeat billing issue; refund issued 2024-09."),
        ("CUST002", "profile", "chat",   1, "technical", "Android crash — resolved after reinstall."),
        ("CUST003", "profile", "email",  0, "general",   "New customer; no prior complaints."),
    ]
    cur.executemany("""
        INSERT OR IGNORE INTO profiles
            (customer_id, namespace, preferred_channel, complaint_count, last_category, notes)
        VALUES (?, ?, ?, ?, ?, ?)
    """, profiles)

    # ---- Past complaints ----
    complaints = [
        # CUST001 — two prior billing complaints
        ("CUST001", "CONV-001-A", "2024-09-01 10:00:00",
         "I was double-charged in August.",
         "billing",
         "We confirmed the duplicate and issued a refund within 5 business days."),
        ("CUST001", "CONV-001-B", "2024-10-05 14:30:00",
         "My invoice shows a charge I don't recognise.",
         "billing",
         "The charge was for an annual plan auto-renewal. We sent the customer a breakdown."),

        # CUST002 — one prior technical complaint
        ("CUST002", "CONV-002-A", "2024-09-20 09:15:00",
         "The app crashes on Android when I open the camera.",
         "technical",
         "Advised customer to clear cache and update to latest app version. Issue resolved."),

        # CUST003 — no prior complaints (seed row left empty intentionally)
    ]
    cur.executemany("""
        INSERT OR IGNORE INTO complaints
            (customer_id, conversation_id, timestamp, complaint, category, response)
        VALUES (?, ?, ?, ?, ?, ?)
    """, complaints)

    conn.commit()
    conn.close()
    print(f"[seed_db] Seeded {len(profiles)} profiles and {len(complaints)} past complaints.")


def store_complaint(
    customer_id: str,
    conversation_id: str,
    complaint: str,
    category: str,
    response: str,
) -> None:
    """Called by the main graph after each resolved complaint."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO complaints (customer_id, conversation_id, complaint, category, response)
        VALUES (?, ?, ?, ?, ?)
    """, (customer_id, conversation_id, complaint, category, response))

    # Update profile count and last category
    cur.execute("""
        INSERT INTO profiles (customer_id, namespace, complaint_count, last_category)
        VALUES (?, 'profile', 1, ?)
        ON CONFLICT(customer_id) DO UPDATE SET
            complaint_count = complaint_count + 1,
            last_category   = excluded.last_category
    """, (customer_id, category))

    conn.commit()
    conn.close()


def load_customer_history(customer_id: str, limit: int = 3) -> str:
    """Return the last `limit` complaints for a customer as a formatted string.
    Returns empty string if the customer has no history."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT timestamp, category, complaint, response
        FROM complaints
        WHERE customer_id = ?
        ORDER BY timestamp DESC
        LIMIT ?
    """, (customer_id, limit))
    rows = cur.fetchall()
    conn.close()

    if not rows:
        return ""

    parts = [f"[Prior complaint history for customer {customer_id}]"]
    for r in reversed(rows):          # show oldest-first for context
        parts.append(
            f"  [{r['timestamp']}] Category={r['category']}\n"
            f"  Complaint: {r['complaint']}\n"
            f"  Agent response: {r['response']}"
        )
    return "\n".join(parts)


def load_profile(customer_id: str) -> dict:
    """Return the long-term profile dict for a customer, or defaults."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM profiles WHERE customer_id = ?", (customer_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        return dict(row)
    return {
        "customer_id": customer_id,
        "namespace": "profile",
        "preferred_channel": "unknown",
        "complaint_count": 0,
        "last_category": None,
        "notes": "",
    }


def reset_db() -> None:
    """Drop tables to allow a clean reset."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS complaints")
    cur.execute("DROP TABLE IF EXISTS profiles")
    conn.commit()
    conn.close()


if __name__ == "__main__":
    reset_db()
    init_db()
    seed_data()
    conn = get_connection()
    n_profiles  = conn.execute("SELECT COUNT(*) FROM profiles").fetchone()[0]
    n_complaints = conn.execute("SELECT COUNT(*) FROM complaints").fetchone()[0]
    conn.close()
    print(f"[seed_db] DB reset & ready: {n_profiles} profiles, {n_complaints} complaints in {DB_PATH}")
