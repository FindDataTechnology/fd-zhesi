"""个人层存储（task 3.1）：立场卡 / 张力簿 / 思想年轮。

物理分库铁律（spec「个人层私有归属」）：本库是 fd-zhesi 产品自有存储
（默认 ~/.fd-zhesi/personal.db，env FD_ZHESI_DB），与参照系库
（fd-zhesi-reference 的 reference.db）物理分离——参照系是可重建缓存，
个人层是用户信念记录，永不混入共享底座。

migration 链：MIGRATIONS 列表按序执行、幂等（user_version 门），
新增迁移只追加不改动历史项。
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

MIGRATIONS = [
    # 0001：立场卡 + 年轮 + 张力簿 + 审计
    """
    CREATE TABLE stance_cards (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        question TEXT NOT NULL,
        question_ref TEXT,
        position TEXT NOT NULL,
        reasons TEXT,
        strongest_objection TEXT,
        my_response TEXT,
        status TEXT NOT NULL DEFAULT 'active',      -- active | sealed
        stability TEXT NOT NULL DEFAULT 'stable',   -- stable | wavering | shelved
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        sealed_at TEXT
    );
    CREATE INDEX idx_cards_user ON stance_cards(user_id, status);
    CREATE TABLE annals (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        card_id TEXT NOT NULL,
        kind TEXT NOT NULL,                         -- sealed | superseded
        snapshot TEXT NOT NULL,                     -- 卡片完整 JSON 快照
        at TEXT NOT NULL
    );
    CREATE INDEX idx_annals_user ON annals(user_id, at);
    CREATE TABLE tensions (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        card_ids TEXT NOT NULL,                     -- JSON array
        description TEXT NOT NULL,
        source TEXT,                                -- 参照系张力来源（4.4 写入）
        status TEXT NOT NULL DEFAULT 'open',        -- open | resolved
        created_at TEXT NOT NULL,
        resolved_at TEXT
    );
    CREATE TABLE audit_log (
        id TEXT PRIMARY KEY,
        user_id TEXT,
        action TEXT NOT NULL,
        resource TEXT,
        outcome TEXT NOT NULL,                      -- allowed | denied
        detail TEXT,
        at TEXT NOT NULL
    );
    """,
    # 0002：跨线契约授权（task 5.1）——用户对消费方（如剧创）开放哪类卡
    """
    CREATE TABLE grants (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        consumer TEXT NOT NULL,                     -- 如 juchuang
        card_kinds TEXT NOT NULL,                   -- JSON array: stance/tension
        granted_at TEXT NOT NULL,
        revoked_at TEXT
    );
    CREATE INDEX idx_grants_user ON grants(user_id, consumer);
    """,
    # 0003：谱闭环投影（task 4.3）——版本化保留历史（思想年轮的投影面）
    """
    CREATE TABLE projections (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        axes_version TEXT NOT NULL,
        axes TEXT NOT NULL,                         -- JSON {axis: value}
        neighbors TEXT NOT NULL,                    -- JSON [{atlas_id,name_en,name_zh,distance}]
        based_on_cards TEXT NOT NULL,               -- JSON [card_id]
        created_at TEXT NOT NULL
    );
    CREATE INDEX idx_projections_user ON projections(user_id, created_at);
    """,
    # 0004：Atlas 降级标注（zhesi-atlas-resilience 2.1/2.2）+ 论证结构（4.1）
    """
    ALTER TABLE projections ADD COLUMN missing_layers TEXT;  -- JSON [layer]
    ALTER TABLE projections ADD COLUMN confidence REAL;
    ALTER TABLE stance_cards ADD COLUMN argument TEXT;       -- JSON 论证结构（可选）
    """,
    # 0005：张力候选与类型/状态（5.4-5.6）
    """
    ALTER TABLE tensions ADD COLUMN kind TEXT NOT NULL DEFAULT 'confirmed';
    ALTER TABLE tensions ADD COLUMN basis TEXT;              -- JSON 推断依据（候选）
    ALTER TABLE tensions ADD COLUMN tension_type TEXT NOT NULL DEFAULT 'contradiction';
    CREATE TABLE tension_events (
        id TEXT PRIMARY KEY,
        tension_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        from_status TEXT,
        to_status TEXT NOT NULL,
        at TEXT NOT NULL,
        detail TEXT
    );
    CREATE INDEX idx_tension_events ON tension_events(tension_id, at);
    """,
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(db_path: str | None = None) -> sqlite3.Connection:
    path = db_path or os.environ.get("FD_ZHESI_DB", "")
    if not path:
        path = str(Path.home() / ".fd-zhesi" / "personal.db")
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def migrate(conn: sqlite3.Connection) -> int:
    """按序应用未执行的迁移（user_version 门，幂等可重放）。"""
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    for i, ddl in enumerate(MIGRATIONS, start=1):
        if i > current:
            conn.executescript(ddl)
            conn.execute(f"PRAGMA user_version = {i}")
            conn.commit()
    return len(MIGRATIONS)


def new_id() -> str:
    return uuid.uuid4().hex[:12]


# ---- 立场卡生命周期（task 3.2 的数据面） ----

def card_row_to_dict(r: sqlite3.Row) -> dict:
    return {
        "id": r["id"],
        "question": r["question"],
        "question_ref": r["question_ref"],
        "position": r["position"],
        "reasons": r["reasons"],
        "strongest_objection": r["strongest_objection"],
        "my_response": r["my_response"],
        "status": r["status"],
        "stability": r["stability"],
        "argument": _argument_of(r),
        "created_at": r["created_at"],
        "updated_at": r["updated_at"],
        "sealed_at": r["sealed_at"],
    }


def empty_argument(position: str = "") -> dict:
    """空论证结构：旧卡（0004 之前）与未填论证的卡都以此形态读取。"""
    return {"claim": position or None, "premises": [], "edges": []}


def _argument_of(r: sqlite3.Row) -> dict:
    """读 argument 列（旧库/旧行没有该列或为 NULL → 空论证，不抛错）。"""
    try:
        raw = r["argument"]
    except (IndexError, KeyError):
        raw = None
    if not raw:
        return empty_argument(r["position"])
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return empty_argument(r["position"])
    if not isinstance(parsed, dict):
        return empty_argument(r["position"])
    return {
        "claim": parsed.get("claim") or r["position"],
        "premises": parsed.get("premises") or [],
        "edges": parsed.get("edges") or [],
    }


def set_argument(
    conn: sqlite3.Connection, user_id: str, card_id: str, argument: dict,
) -> dict | None:
    """写入论证结构（散文式字段不动；spec「结构化论证与散文字段共存」）。"""
    card = get_card(conn, user_id, card_id)
    if not card or card["status"] != "active":
        return None
    conn.execute(
        "UPDATE stance_cards SET argument=?, updated_at=? WHERE id=?",
        (json.dumps(argument, ensure_ascii=False), now(), card_id),
    )
    conn.commit()
    return get_card(conn, user_id, card_id)


def create_card(
    conn: sqlite3.Connection, user_id: str, question: str, position: str,
    reasons: str | None = None, question_ref: str | None = None,
) -> dict:
    ts = now()
    cid = new_id()
    conn.execute(
        "INSERT INTO stance_cards (id, user_id, question, question_ref, position,"
        " reasons, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
        (cid, user_id, question, question_ref, position, reasons, ts, ts),
    )
    conn.commit()
    return get_card(conn, user_id, cid)


def get_card(conn: sqlite3.Connection, user_id: str, card_id: str) -> dict | None:
    r = conn.execute(
        "SELECT * FROM stance_cards WHERE id=? AND user_id=?", (card_id, user_id)
    ).fetchone()
    return card_row_to_dict(r) if r else None


def list_cards(conn: sqlite3.Connection, user_id: str, status: str = "active") -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM stance_cards WHERE user_id=? AND status=? ORDER BY created_at",
        (user_id, status),
    ).fetchall()
    return [card_row_to_dict(r) for r in rows]


def record_objection(
    conn: sqlite3.Connection, user_id: str, card_id: str, objection: str,
) -> dict | None:
    card = get_card(conn, user_id, card_id)
    if not card or card["status"] != "active":
        return None
    conn.execute(
        "UPDATE stance_cards SET strongest_objection=?, updated_at=? WHERE id=?",
        (objection, now(), card_id),
    )
    conn.commit()
    return get_card(conn, user_id, card_id)


def record_response(
    conn: sqlite3.Connection, user_id: str, card_id: str,
    my_response: str, stability: str | None = None,
) -> dict | None:
    """辩闭环呈现反驳后用户回应：回应入卡、现状随之更新（spec「承受反驳并回应」）。"""
    card = get_card(conn, user_id, card_id)
    if not card or card["status"] != "active":
        return None
    new_stability = stability or card["stability"]
    if new_stability not in ("stable", "wavering", "shelved"):
        raise ValueError("stability 必须是 stable/wavering/shelved")
    conn.execute(
        "UPDATE stance_cards SET my_response=?, stability=?, updated_at=? WHERE id=?",
        (my_response, new_stability, now(), card_id),
    )
    conn.commit()
    return get_card(conn, user_id, card_id)


def change_position(
    conn: sqlite3.Connection, user_id: str, card_id: str,
    new_position: str, reasons: str | None = None,
) -> dict | None:
    """立场变更：旧卡封存进年轮（完整历史），新卡开卡（spec「立场变更入年轮」）。"""
    card = get_card(conn, user_id, card_id)
    if not card or card["status"] != "active":
        return None
    ts = now()
    conn.execute(
        "UPDATE stance_cards SET status='sealed', sealed_at=?, updated_at=? WHERE id=?",
        (ts, ts, card_id),
    )
    conn.execute(
        "INSERT INTO annals (id, user_id, card_id, kind, snapshot, at) VALUES (?,?,?,?,?,?)",
        (new_id(), user_id, card_id, "superseded", json.dumps(card, ensure_ascii=False), ts),
    )
    new_cid = new_id()
    conn.execute(
        "INSERT INTO stance_cards (id, user_id, question, question_ref, position,"
        " reasons, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
        (
            new_cid, user_id, card["question"], card["question_ref"],
            new_position, reasons or card["reasons"], ts, ts,
        ),
    )
    conn.commit()
    return get_card(conn, user_id, new_cid)


def list_annals(conn: sqlite3.Connection, user_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM annals WHERE user_id=? ORDER BY at", (user_id,)
    ).fetchall()
    return [
        {
            "id": r["id"],
            "card_id": r["card_id"],
            "kind": r["kind"],
            "snapshot": json.loads(r["snapshot"]),
            "at": r["at"],
        }
        for r in rows
    ]


# ---- 审计（task 3.3 的留痕面） ----

def audit(
    conn: sqlite3.Connection, user_id: str | None, action: str,
    resource: str | None, outcome: str, detail: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO audit_log (id, user_id, action, resource, outcome, detail, at)"
        " VALUES (?,?,?,?,?,?,?)",
        (new_id(), user_id, action, resource, outcome, detail, now()),
    )
    conn.commit()


# ---- 张力簿（5.4-5.6：候选与既成分离、类型与状态可追溯） ----

TENSION_TYPES = (
    "contradiction",
    "presupposition-conflict",
    "value-conflict",
    "empirical-dispute",
)
TENSION_STATUSES = ("open", "resolved", "dissolved")
TENSION_KINDS = ("confirmed", "candidate")


def tension_row_to_dict(r: sqlite3.Row) -> dict:
    def _col(name, default=None):
        try:
            return r[name]
        except (IndexError, KeyError):
            return default

    basis_raw = _col("basis")
    try:
        basis = json.loads(basis_raw) if basis_raw else None
    except (TypeError, ValueError):
        basis = None
    return {
        "id": r["id"],
        "card_ids": json.loads(r["card_ids"]),
        "description": r["description"],
        "source": r["source"],
        "status": r["status"],
        "kind": _col("kind", "confirmed"),
        "tension_type": _col("tension_type", "contradiction"),
        "basis": basis,
        "created_at": r["created_at"],
        "resolved_at": r["resolved_at"],
    }


def record_tension_event(
    conn: sqlite3.Connection, user_id: str, tension_id: str,
    from_status: str | None, to_status: str, detail: str | None = None,
) -> None:
    """状态流转留痕（spec「状态变化可追溯」）。"""
    conn.execute(
        "INSERT INTO tension_events (id, tension_id, user_id, from_status, to_status, at, detail)"
        " VALUES (?,?,?,?,?,?,?)",
        (new_id(), tension_id, user_id, from_status, to_status, now(), detail),
    )
    conn.commit()


def tension_events(conn: sqlite3.Connection, user_id: str, tension_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM tension_events WHERE tension_id=? AND user_id=? ORDER BY at, rowid",
        (tension_id, user_id),
    ).fetchall()
    return [
        {
            "id": r["id"],
            "from_status": r["from_status"],
            "to_status": r["to_status"],
            "at": r["at"],
            "detail": r["detail"],
        }
        for r in rows
    ]


def update_tension_status(
    conn: sqlite3.Connection, user_id: str, tension_id: str,
    new_status: str, detail: str | None = None,
) -> dict | None:
    """张力状态流转（open → resolved / dissolved；候选 → confirmed 亦走此路）。"""
    if new_status not in TENSION_STATUSES:
        raise ValueError(f"status 只支持 {list(TENSION_STATUSES)}")
    row = conn.execute(
        "SELECT * FROM tensions WHERE id=? AND user_id=?", (tension_id, user_id)
    ).fetchone()
    if row is None:
        return None
    old = row["status"]
    if old == new_status:
        return tension_row_to_dict(row)
    ts = now()
    conn.execute(
        "UPDATE tensions SET status=?, resolved_at=? WHERE id=?",
        (new_status, ts if new_status != "open" else None, tension_id),
    )
    conn.commit()
    record_tension_event(conn, user_id, tension_id, old, new_status, detail)
    row = conn.execute(
        "SELECT * FROM tensions WHERE id=?", (tension_id,)
    ).fetchone()
    return tension_row_to_dict(row)


def confirm_tension(
    conn: sqlite3.Connection, user_id: str, tension_id: str,
) -> dict | None:
    """候选升级为既成张力（kind: candidate → confirmed，状态保持 open）。"""
    row = conn.execute(
        "SELECT * FROM tensions WHERE id=? AND user_id=?", (tension_id, user_id)
    ).fetchone()
    if row is None:
        return None
    conn.execute("UPDATE tensions SET kind='confirmed' WHERE id=?", (tension_id,))
    conn.commit()
    record_tension_event(conn, user_id, tension_id, row["status"], row["status"],
                         detail="candidate→confirmed")
    row = conn.execute("SELECT * FROM tensions WHERE id=?", (tension_id,)).fetchone()
    return tension_row_to_dict(row)


# ---- 跨线契约授权（task 5.1 的数据面） ----

def grant(
    conn: sqlite3.Connection, user_id: str, consumer: str, card_kinds: list[str],
) -> dict:
    valid = {"stance", "tension"}
    if not set(card_kinds) <= valid:
        raise ValueError(f"card_kinds 只支持 {sorted(valid)}")
    gid = new_id()
    conn.execute(
        "INSERT INTO grants (id, user_id, consumer, card_kinds, granted_at)"
        " VALUES (?,?,?,?,?)",
        (gid, user_id, consumer, json.dumps(sorted(set(card_kinds))), now()),
    )
    conn.commit()
    return {"id": gid, "consumer": consumer, "card_kinds": sorted(set(card_kinds))}


def active_grant(
    conn: sqlite3.Connection, user_id: str, consumer: str,
) -> dict | None:
    r = conn.execute(
        "SELECT * FROM grants WHERE user_id=? AND consumer=? AND revoked_at IS NULL"
        " ORDER BY granted_at DESC LIMIT 1",
        (user_id, consumer),
    ).fetchone()
    if not r:
        return None
    return {"id": r["id"], "card_kinds": json.loads(r["card_kinds"])}
