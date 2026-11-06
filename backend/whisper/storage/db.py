"""Offline SQLite Database Manager for WhisperProtocol."""

import os
from pathlib import Path
import sqlite3
import time
from typing import Any, Dict, List, Optional


def get_default_db_path() -> str:
    """Return platform-appropriate local application database path."""
    home = Path.home()
    if os.name == "nt":  # Windows
        app_data = os.environ.get("APPDATA", str(home / "AppData" / "Roaming"))
        base_dir = Path(app_data) / "WhisperProtocol"
    elif os.name == "posix":
        if "darwin" in os.sys.platform:  # macOS
            base_dir = home / "Library" / "Application Support" / "WhisperProtocol"
        else:  # Linux
            xdg_data = os.environ.get("XDG_DATA_HOME", str(home / ".local" / "share"))
            base_dir = Path(xdg_data) / "whisperprotocol"
    else:
        base_dir = home / ".whisperprotocol"

    base_dir.mkdir(parents=True, exist_ok=True)
    return str(base_dir / "whisper.db")


def generate_unique_alias() -> str:
    """Generate a clean, unique machine alias (e.g. Whisper-MacAir-7A3F or Whisper-7A3F)."""
    import socket
    import secrets
    suffix = secrets.token_hex(2).upper()
    try:
        host = socket.gethostname().split(".")[0]
        clean_host = "".join(c for c in host if c.isalnum() or c in "-_")[:6]
        if clean_host and clean_host.lower() not in ("localhost", "unknown"):
            return f"Whisper-{clean_host}-{suffix}"
    except Exception:
        pass
    return f"Whisper-{suffix}"


class DatabaseManager:
    """Thread-safe SQLite manager for offline settings, node history, and transfer logs."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or get_default_db_path()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Create tables if they don't already exist."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Settings table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)

            # Discovered / Paired nodes table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS discovered_nodes (
                    alias TEXT PRIMARY KEY,
                    session_id INTEGER,
                    last_seen REAL NOT NULL,
                    rssi_db REAL DEFAULT 0.0,
                    profile TEXT DEFAULT 'ultrasonic',
                    trust_status TEXT DEFAULT 'unpaired'
                )
            """)

            # Transfer sessions history
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS transfer_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    direction TEXT NOT NULL,
                    peer_alias TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    sas_code TEXT,
                    error_message TEXT,
                    created_at REAL NOT NULL,
                    completed_at REAL
                )
            """)

            # Default initial settings if empty
            cursor.execute("SELECT COUNT(*) FROM settings")
            if cursor.fetchone()[0] == 0:
                defaults = [
                    ("alias", generate_unique_alias()),
                    ("profile", "ultrasonic"),
                    ("sample_rate", "48000"),
                    ("ecc_symbols", "8"),
                    ("auto_calibrate", "true"),
                ]
                now = time.time()
                cursor.executemany(
                    "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
                    [(k, v, now) for k, v in defaults],
                )
            else:
                # Migrate generic "WhisperNode" to machine-unique alias
                cursor.execute("SELECT value FROM settings WHERE key = 'alias'")
                row = cursor.fetchone()
                if row and (row["value"] == "WhisperNode" or not row["value"]):
                    cursor.execute(
                        "UPDATE settings SET value = ?, updated_at = ? WHERE key = 'alias'",
                        (generate_unique_alias(), time.time()),
                    )

            conn.commit()

    # ─── Settings API ────────────────────────────────────────────────────────────

    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """, (key, str(value), time.time()))
            conn.commit()

    def get_all_settings(self) -> Dict[str, str]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM settings")
            return {row["key"]: row["value"] for row in cursor.fetchall()}

    # ─── Nodes API ───────────────────────────────────────────────────────────────

    def upsert_node(
        self,
        alias: str,
        session_id: int = 0,
        rssi_db: float = 0.0,
        profile: str = "ultrasonic",
        trust_status: str = "unpaired",
    ) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO discovered_nodes (alias, session_id, last_seen, rssi_db, profile, trust_status)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(alias) DO UPDATE SET
                    session_id = excluded.session_id,
                    last_seen = excluded.last_seen,
                    rssi_db = excluded.rssi_db,
                    profile = excluded.profile
            """, (alias, session_id, time.time(), rssi_db, profile, trust_status))
            conn.commit()

    def get_nodes(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM discovered_nodes ORDER BY last_seen DESC")
            return [dict(row) for row in cursor.fetchall()]

    def delete_node(self, alias: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM discovered_nodes WHERE alias = ?", (alias,))
            conn.commit()
            return cursor.rowcount > 0

    # ─── Transfer History API ────────────────────────────────────────────────────

    def record_transfer(
        self,
        session_id: int,
        direction: str,
        peer_alias: str,
        file_name: str,
        file_size: int,
        status: str,
        sas_code: Optional[str] = None,
        error_message: Optional[str] = None,
        created_at: Optional[float] = None,
        completed_at: Optional[float] = None,
    ) -> int:
        now = time.time()
        c_at = created_at if created_at is not None else now
        fin_at = completed_at if completed_at is not None else (now if status in ("completed", "declined", "failed") else None)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO transfer_history (
                    session_id, direction, peer_alias, file_name, file_size,
                    status, sas_code, error_message, created_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (session_id, direction, peer_alias, file_name, file_size, status, sas_code, error_message, c_at, fin_at))
            conn.commit()
            return cursor.lastrowid

    def get_transfer_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM transfer_history ORDER BY created_at DESC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def clear_history(self) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM transfer_history")
            conn.commit()
