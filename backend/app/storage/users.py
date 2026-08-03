"""User accounts stored in SQLite (same DB file as the document registry).

Login is employee_id + date of birth (YYYY-MM-DD). Role controls admin vs employee.
"""
from __future__ import annotations

import sqlite3
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class UserRecord:
    id: str
    employee_id: str
    dob: str  # YYYY-MM-DD
    name: str
    role: str  # admin | employee


class UserStore:
    def __init__(self, db_path: str):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    employee_id TEXT NOT NULL UNIQUE,
                    dob TEXT NOT NULL,
                    name TEXT NOT NULL,
                    role TEXT NOT NULL
                )
                """
            )
            # Migrate away from older username/password schema if present.
            cols = {r[1] for r in self._conn.execute("PRAGMA table_info(users)").fetchall()}
            if "employee_id" not in cols:
                self._conn.execute("DROP TABLE users")
                self._conn.execute(
                    """
                    CREATE TABLE users (
                        id TEXT PRIMARY KEY,
                        employee_id TEXT NOT NULL UNIQUE,
                        dob TEXT NOT NULL,
                        name TEXT NOT NULL,
                        role TEXT NOT NULL
                    )
                    """
                )

    def get_by_employee_id(self, employee_id: str) -> Optional[UserRecord]:
        cur = self._conn.execute(
            "SELECT * FROM users WHERE employee_id = ?", (employee_id.strip().upper(),)
        )
        row = cur.fetchone()
        return self._row(row) if row else None

    def create(self, employee_id: str, dob: str, name: str, role: str) -> UserRecord:
        user_id = str(uuid.uuid4())
        emp = employee_id.strip().upper()
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO users (id, employee_id, dob, name, role) VALUES (?, ?, ?, ?, ?)",
                (user_id, emp, dob.strip(), name.strip(), role),
            )
        return UserRecord(id=user_id, employee_id=emp, dob=dob.strip(), name=name.strip(), role=role)

    @staticmethod
    def _row(row: sqlite3.Row) -> UserRecord:
        return UserRecord(
            id=row["id"],
            employee_id=row["employee_id"],
            dob=row["dob"],
            name=row["name"],
            role=row["role"],
        )
