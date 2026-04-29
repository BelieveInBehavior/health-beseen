import aiosqlite
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "health.db")


async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    return db


async def init_db():
    db = await get_db()
    try:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS assessment (
                id TEXT PRIMARY KEY,
                user_input TEXT NOT NULL,
                symptoms TEXT NOT NULL,
                risk_level TEXT NOT NULL,
                advice TEXT NOT NULL,
                evidence TEXT NOT NULL,
                matched_rules TEXT NOT NULL,
                all_rules TEXT NOT NULL,
                rule_version TEXT NOT NULL,
                model_version TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS event_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_name TEXT NOT NULL,
                assessment_id TEXT,
                payload TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audit_record (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                assessment_id TEXT NOT NULL,
                matched_rules TEXT NOT NULL,
                rule_version TEXT NOT NULL,
                model_version TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (assessment_id) REFERENCES assessment(id)
            );

            CREATE TABLE IF NOT EXISTS contact_request (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                assessment_id TEXT NOT NULL,
                reason TEXT,
                status TEXT DEFAULT 'pending',
                created_at TEXT NOT NULL,
                FOREIGN KEY (assessment_id) REFERENCES assessment(id)
            );
        """)
        await db.commit()
    finally:
        await db.close()
