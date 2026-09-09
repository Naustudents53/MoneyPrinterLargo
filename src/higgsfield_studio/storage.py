"""SQLite storage for Higgsfield Studio projects."""
from __future__ import annotations
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from .models import ProductionProject, Phase


class ProjectStorage:
    """Thread-safe SQLite storage for production projects."""

    def __init__(self, db_path: Path | str):
        self._db_path = str(db_path)
        self._local = threading.local()
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(self._db_path, timeout=30)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA foreign_keys=ON")
        return self._local.conn

    def _init_db(self):
        conn = self._conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                version INTEGER DEFAULT 1,
                title TEXT NOT NULL DEFAULT '',
                topic TEXT NOT NULL DEFAULT '',
                phase TEXT NOT NULL DEFAULT 'init',
                progress REAL DEFAULT 0.0,
                config_json TEXT DEFAULT '{}',
                data_json TEXT DEFAULT '{}',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                job_id TEXT DEFAULT '',
                error TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS project_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                data_json TEXT NOT NULL,
                created_at REAL NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id)
            );

            CREATE TABLE IF NOT EXISTS shots (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                scene_id TEXT DEFAULT '',
                sequence INTEGER DEFAULT 0,
                status TEXT DEFAULT 'planned',
                data_json TEXT DEFAULT '{}',
                FOREIGN KEY (project_id) REFERENCES projects(id)
            );

            CREATE TABLE IF NOT EXISTS cost_events (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                shot_id TEXT DEFAULT '',
                provider TEXT DEFAULT '',
                model TEXT DEFAULT '',
                estimated REAL,
                actual REAL,
                timestamp REAL NOT NULL,
                description TEXT DEFAULT '',
                FOREIGN KEY (project_id) REFERENCES projects(id)
            );

            CREATE TABLE IF NOT EXISTS prompt_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prompt_hash TEXT NOT NULL,
                prompt TEXT NOT NULL,
                style TEXT DEFAULT '',
                shot_type TEXT DEFAULT '',
                model TEXT DEFAULT '',
                quality_score REAL DEFAULT 0,
                success INTEGER DEFAULT 0,
                regeneration_count INTEGER DEFAULT 0,
                created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS assets (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                type TEXT DEFAULT '',
                path TEXT DEFAULT '',
                purpose TEXT DEFAULT '',
                metadata_json TEXT DEFAULT '{}',
                created_at REAL NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id)
            );

            CREATE TABLE IF NOT EXISTS learning_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                category TEXT NOT NULL,
                key TEXT NOT NULL,
                value_json TEXT DEFAULT '{}',
                created_at REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_shots_project ON shots(project_id);
            CREATE INDEX IF NOT EXISTS idx_costs_project ON cost_events(project_id);
            CREATE INDEX IF NOT EXISTS idx_prompt_memory_hash ON prompt_memory(prompt_hash);
            CREATE INDEX IF NOT EXISTS idx_assets_project ON assets(project_id);
            CREATE INDEX IF NOT EXISTS idx_versions_project ON project_versions(project_id);
        """)
        conn.commit()

    def save_project(self, project: ProductionProject) -> None:
        project.updated_at = time.time()
        data = project.to_dict()
        config_json = json.dumps(data.pop("config", {}))
        conn = self._conn()
        conn.execute("""
            INSERT INTO projects (id, version, title, topic, phase, progress,
                                  config_json, data_json, created_at, updated_at,
                                  job_id, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                version=excluded.version, title=excluded.title, topic=excluded.topic,
                phase=excluded.phase, progress=excluded.progress,
                config_json=excluded.config_json, data_json=excluded.data_json,
                updated_at=excluded.updated_at, job_id=excluded.job_id, error=excluded.error
        """, (
            project.id, project.version, project.config.title, project.config.topic,
            project.phase.value, project.progress, config_json,
            json.dumps(data), project.created_at, project.updated_at,
            project.job_id, project.error,
        ))
        conn.commit()

    def save_version(self, project: ProductionProject) -> None:
        data = project.to_dict()
        conn = self._conn()
        conn.execute("""
            INSERT INTO project_versions (project_id, version, data_json, created_at)
            VALUES (?, ?, ?, ?)
        """, (project.id, project.version, json.dumps(data), time.time()))
        conn.commit()

    def load_project(self, project_id: str) -> ProductionProject | None:
        conn = self._conn()
        row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        if not row:
            return None
        data = json.loads(row["data_json"])
        data["config"] = json.loads(row["config_json"])
        data["id"] = row["id"]
        data["version"] = row["version"]
        data["phase"] = row["phase"]
        data["progress"] = row["progress"]
        data["created_at"] = row["created_at"]
        data["updated_at"] = row["updated_at"]
        data["job_id"] = row["job_id"] or ""
        data["error"] = row["error"] or ""
        return ProductionProject.from_dict(data)

    def list_projects(self, limit: int = 50, offset: int = 0) -> list[dict]:
        conn = self._conn()
        rows = conn.execute("""
            SELECT id, version, title, topic, phase, progress,
                   created_at, updated_at, job_id, error
            FROM projects ORDER BY updated_at DESC LIMIT ? OFFSET ?
        """, (limit, offset)).fetchall()
        return [dict(r) for r in rows]

    def delete_project(self, project_id: str) -> bool:
        conn = self._conn()
        conn.execute("DELETE FROM cost_events WHERE project_id=?", (project_id,))
        conn.execute("DELETE FROM shots WHERE project_id=?", (project_id,))
        conn.execute("DELETE FROM assets WHERE project_id=?", (project_id,))
        conn.execute("DELETE FROM project_versions WHERE project_id=?", (project_id,))
        cur = conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
        conn.commit()
        return cur.rowcount > 0

    def save_cost_event(self, project_id: str, event: dict) -> None:
        conn = self._conn()
        conn.execute("""
            INSERT INTO cost_events (id, project_id, shot_id, provider, model,
                                     estimated, actual, timestamp, description)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            event.get("id", ""), project_id, event.get("shot_id", ""),
            event.get("provider", ""), event.get("model", ""),
            event.get("estimated"), event.get("actual"),
            event.get("timestamp", time.time()), event.get("description", ""),
        ))
        conn.commit()

    def get_project_costs(self, project_id: str) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM cost_events WHERE project_id=? ORDER BY timestamp",
            (project_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def save_prompt_memory(self, entry: dict) -> None:
        conn = self._conn()
        conn.execute("""
            INSERT INTO prompt_memory (prompt_hash, prompt, style, shot_type,
                                       model, quality_score, success,
                                       regeneration_count, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            entry.get("prompt_hash", ""), entry.get("prompt", ""),
            entry.get("style", ""), entry.get("shot_type", ""),
            entry.get("model", ""), entry.get("quality_score", 0),
            int(entry.get("success", False)), entry.get("regeneration_count", 0),
            time.time(),
        ))
        conn.commit()

    def get_best_prompts(self, style: str = "", shot_type: str = "",
                         limit: int = 10) -> list[dict]:
        conn = self._conn()
        query = "SELECT * FROM prompt_memory WHERE success=1"
        params: list = []
        if style:
            query += " AND style=?"
            params.append(style)
        if shot_type:
            query += " AND shot_type=?"
            params.append(shot_type)
        query += " ORDER BY quality_score DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def save_asset(self, project_id: str, asset: dict) -> None:
        conn = self._conn()
        conn.execute("""
            INSERT OR REPLACE INTO assets (id, project_id, type, path, purpose,
                                           metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            asset.get("id", ""), project_id, asset.get("type", ""),
            asset.get("path", ""), asset.get("purpose", ""),
            json.dumps(asset.get("metadata", {})), time.time(),
        ))
        conn.commit()

    def get_project_assets(self, project_id: str) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM assets WHERE project_id=? ORDER BY created_at", (project_id,)
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["metadata"] = json.loads(d.pop("metadata_json", "{}"))
            result.append(d)
        return result

    def save_learning_stat(self, project_id: str, category: str,
                           key: str, value: Any) -> None:
        conn = self._conn()
        conn.execute("""
            INSERT INTO learning_stats (project_id, category, key, value_json, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (project_id, category, key, json.dumps(value), time.time()))
        conn.commit()

    def get_learning_stats(self, category: str = "", limit: int = 100) -> list[dict]:
        conn = self._conn()
        query = "SELECT * FROM learning_stats"
        params: list = []
        if category:
            query += " WHERE category=?"
            params.append(category)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["value"] = json.loads(d.pop("value_json", "{}"))
            result.append(d)
        return result

    def list_versions(self, project_id: str) -> list[dict]:
        conn = self._conn()
        rows = conn.execute("""
            SELECT id, version, created_at FROM project_versions
            WHERE project_id=? ORDER BY version DESC
        """, (project_id,)).fetchall()
        return [dict(r) for r in rows]

    def load_version(self, project_id: str, version: int) -> ProductionProject | None:
        conn = self._conn()
        row = conn.execute("""
            SELECT data_json FROM project_versions
            WHERE project_id=? AND version=?
        """, (project_id, version)).fetchone()
        if not row:
            return None
        data = json.loads(row["data_json"])
        return ProductionProject.from_dict(data)

    def close(self):
        if hasattr(self._local, 'conn') and self._local.conn:
            self._local.conn.close()
            self._local.conn = None


def get_storage(db_dir: Path | str | None = None) -> ProjectStorage:
    """Get or create the project storage instance."""
    if db_dir is None:
        import sys, os
        root = os.path.dirname(sys.path[0]) if sys.path[0] else os.getcwd()
        db_dir = os.path.join(root, ".mp", "higgsfield")
    db_dir = Path(db_dir)
    db_dir.mkdir(parents=True, exist_ok=True)
    return ProjectStorage(db_dir / "studio.db")
