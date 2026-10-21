"""zhesi-atlas-resilience 5.4-5.6 验证：张力候选、分离展示与类型/状态（全离线）。

- 5.4 候选发现（前提重叠 + 影响图 critical 关系），候选带推断依据
- 5.5 候选与既成分离展示、确认与忽略，状态流转留痕
- 5.6 张力类型与状态字段（词表约束），状态变更可追溯
"""

from __future__ import annotations

import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fd_zhesi_api import cards, personal, synthesis
from fd_zhesi_api.tension_map import TENSION_TYPES

app = FastAPI()
app.include_router(cards.router)
app.include_router(synthesis.router)
client = TestClient(app)
AUTH = {"Authorization": "Bearer dev-tok-alice"}
AUTH_BOB = {"Authorization": "Bearer dev-tok-bob"}

FW_Q = "Free will: compatibilism, libertarianism, or no free will?"
GOD_Q = "God: theism or atheism?"

_STANCES = [
    ("2020", FW_Q, "compatibilism", "相容论", 59.2),
    ("2020", FW_Q, "libertarianism", "自由意志论", 18.8),
    ("2020", FW_Q, "no free will", "无自由意志", 11.2),
    ("2020", GOD_Q, "theism", "有神论", 67.1),
    ("2020", GOD_Q, "atheism", "无神论", 16.8),
]


def _make_ref_db(path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE concepts (
            term TEXT NOT NULL, title TEXT NOT NULL, url TEXT NOT NULL,
            snippet TEXT, retrieved_at TEXT NOT NULL, PRIMARY KEY (term, url));
        CREATE TABLE stances (
            survey_round TEXT NOT NULL, question TEXT NOT NULL, question_zh TEXT,
            option TEXT NOT NULL, option_zh TEXT, pct REAL, retrieved_at TEXT NOT NULL,
            category TEXT, multi_select INTEGER, tabulation TEXT, respondents INTEGER,
            PRIMARY KEY (survey_round, question, option));
        CREATE TABLE philosophers (
            atlas_id INTEGER PRIMARY KEY, name_pt TEXT NOT NULL, name_en TEXT,
            name_zh TEXT, birth_year INTEGER, death_year INTEGER, school TEXT,
            school_en TEXT, school_zh TEXT, region TEXT, region_en TEXT, region_zh TEXT,
            individualism REAL, materialism REAL, rationalism REAL, determinism REAL,
            transcendence REAL, universalism REAL, influence_score REAL,
            wikidata_qid TEXT, ingested_at TEXT NOT NULL);
        CREATE TABLE relations (
            atlas_id INTEGER PRIMARY KEY AUTOINCREMENT, source_id INTEGER NOT NULL,
            target_id INTEGER NOT NULL, weight REAL NOT NULL, polarity TEXT NOT NULL,
            ingested_at TEXT NOT NULL);
        """
    )
    for rd, q, opt, opt_zh, pct in _STANCES:
        conn.execute(
            "INSERT INTO stances (survey_round, question, option, option_zh, pct,"
            " retrieved_at, respondents) VALUES (?,?,?,?,?,?,?)",
            (rd, q, opt, opt_zh, pct, "2026-01-01", 1785),
        )
    conn.execute(
        "INSERT INTO philosophers (atlas_id, name_pt, name_en, name_zh, ingested_at)"
        " VALUES (11, 'Hume', 'David Hume', '大衛·休謨', '2026-01-01')")
    conn.execute(
        "INSERT INTO philosophers (atlas_id, name_pt, name_en, name_zh, ingested_at)"
        " VALUES (33, 'Kant', 'Immanuel Kant', '伊曼努爾·康德', '2026-01-01')")
    conn.execute(
        "INSERT INTO relations (source_id, target_id, weight, polarity, ingested_at)"
        " VALUES (11, 33, 0.9, 'critical', '2026-01-01')")
    conn.commit()
    conn.close()


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    ref = tmp_path / "reference.db"
    _make_ref_db(ref)
    monkeypatch.setenv("FD_ZHESI_REF_DB", str(ref))
    monkeypatch.setenv("FD_ZHESI_DB", str(tmp_path / "personal.db"))
    monkeypatch.setenv(
        "FD_ZHESI_AUTH_DEV_TOKENS", "dev-tok-alice=alice,dev-tok-bob=bob"
    )


def _card(question: str, position: str, *, ref: str | None = None,
          headers: dict = AUTH) -> dict:
    r = client.post("/api/v1/cards", json={
        "question": question, "position": position, "question_ref": ref,
    }, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def _set_argument(card_id: str, premises: list[dict], headers: dict = AUTH) -> None:
    r = client.post(f"/api/v1/cards/{card_id}/argument", json={
        "claim": "c", "premises": premises, "edges": [],
    }, headers=headers)
    assert r.status_code == 200, r.text


def _detect(headers: dict = AUTH) -> dict:
    r = client.post("/api/v1/synthesis/detect-tensions", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


# ------------------------------------------------------ 5.4 候选发现 ----
def test_candidate_from_premise_overlap_with_basis() -> None:
    """两张卡共享前提但结论相反 → 候选，带推断依据（5.4 路径一）。"""
    a = _card(FW_Q, "compatibilism", ref="survey-2020:free will")
    b = _card(FW_Q, "libertarianism", ref="survey-2020:free will")
    shared = {"id": "P1", "text": "道德责任需要行动者能对后果负责"}
    _set_argument(a["id"], [shared, {"id": "P2", "text": "决定论不等于强制"}])
    _set_argument(b["id"], [shared, {"id": "Q1", "text": "自由要求另作选择的可能"}])

    body = _detect()
    assert body["created"] == []                       # 无 curated 命中 → 不伪造既成张力
    assert len(body["candidates"]) == 1
    cand = body["candidates"][0]
    assert cand["kind"] == "candidate"
    assert cand["status"] == "open"
    assert sorted(cand["card_ids"]) == sorted([a["id"], b["id"]])
    basis = cand["basis"]
    assert basis["kind"] == "premise-overlap"
    assert any("P1" in label for label in basis["shared_premises"])
    assert basis["positions"] == ["compatibilism", "libertarianism"]
    assert "前提重叠" in cand["source"]
    assert cand["tension_type"] in TENSION_TYPES


def test_candidate_from_critical_relation_with_basis() -> None:
    """两卡引用影响图中 critical 边两端 → 候选，依据是那条边（5.4 路径二）。"""
    _card("Hume on causation", "skeptical realism")
    _card("Kant on causation", "transcendental idealism")

    body = _detect()
    assert len(body["candidates"]) == 1
    cand = body["candidates"][0]
    basis = cand["basis"]
    assert basis["kind"] == "critical-relation"
    assert basis["edge"]["weight"] == 0.9
    assert "critical" in cand["source"] or "批判" in cand["source"]


def test_candidate_type_rules() -> None:
    """候选类型由结构规则判定，不猜测（5.6 词表）。"""
    from fd_zhesi_api.tension_map import candidate_type

    assert candidate_type(overlap=["P1"], opposed=True) == "contradiction"
    assert candidate_type(overlap=["P1"], opposed=False) == "presupposition-conflict"
    assert candidate_type(overlap=[], opposed=False) == "value-conflict"
    assert "empirical-dispute" in TENSION_TYPES  # 只可人工改判，不自动冒充


def test_no_candidate_without_shared_premise_or_critical_edge() -> None:
    """宁缺毋滥：无共享前提、无 critical 关系 → 零候选。"""
    a = _card(FW_Q, "compatibilism", ref="survey-2020:free will")
    b = _card(FW_Q, "libertarianism", ref="survey-2020:free will")
    _set_argument(a["id"], [{"id": "P1", "text": "甲"}])
    _set_argument(b["id"], [{"id": "P1", "text": "乙"}])
    body = _detect()
    assert body["candidates"] == []
    assert body["checked_pairs"] >= 1


# ------------------------------------------- 5.5/5.6 分离展示与状态流转 ----
def _one_candidate() -> dict:
    a = _card(FW_Q, "compatibilism", ref="survey-2020:free will")
    b = _card(FW_Q, "libertarianism", ref="survey-2020:free will")
    shared = {"id": "P1", "text": "道德责任需要行动者能对后果负责"}
    _set_argument(a["id"], [shared])
    _set_argument(b["id"], [shared])
    body = _detect()
    assert len(body["candidates"]) == 1
    return body["candidates"][0]


def test_list_separates_confirmed_and_candidates() -> None:
    """候选与既成张力在列表里分开成组，表述与状态可区分（5.5）。"""
    # 既成：curated 命中（theism × atheism）
    _card(GOD_Q, "theism", ref="survey-2020:god")
    _card(GOD_Q, "atheism", ref="survey-2020:god")
    _detect()
    # 候选：前提重叠
    _one_candidate()

    r = client.get("/api/v1/synthesis/tensions", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert len(body["confirmed"]) == 1 and len(body["candidates"]) == 1
    assert body["confirmed"][0]["kind"] == "confirmed"
    assert body["candidates"][0]["kind"] == "candidate"
    assert body["confirmed"][0]["tension_type"] in TENSION_TYPES
    # 既成的 source 是哲学史记录，候选的 source 标明是推断
    assert body["confirmed"][0]["source"].startswith("经典张力")
    assert "推断" in body["candidates"][0]["source"]


def test_confirm_candidate_promotes_kind_and_records_event() -> None:
    cand = _one_candidate()
    r = client.post(f"/api/v1/synthesis/tensions/{cand['id']}/confirm", headers=AUTH)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["kind"] == "confirmed"
    assert out["status"] == "open"
    assert any(e["detail"] == "candidate→confirmed" for e in out["events"])
    # 库里也是 confirmed
    conn = personal.connect()
    row = conn.execute("SELECT kind FROM tensions WHERE id=?", (cand["id"],)).fetchone()
    conn.close()
    assert row["kind"] == "confirmed"


def test_ignore_candidate_dissolves_and_keeps_history() -> None:
    cand = _one_candidate()
    r = client.post(f"/api/v1/synthesis/tensions/{cand['id']}/ignore", headers=AUTH)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["status"] == "dissolved"
    assert out["resolved_at"]
    events = out["events"]
    assert [e["to_status"] for e in events] == ["open", "dissolved"]
    # 忽略后不再出现在 open 列表里，但记录仍在（留痕）
    open_list = client.get("/api/v1/synthesis/tensions",
                           params={"status": "open"}, headers=AUTH).json()["results"]
    assert all(t["id"] != cand["id"] for t in open_list)
    all_list = client.get("/api/v1/synthesis/tensions", headers=AUTH).json()["results"]
    assert any(t["id"] == cand["id"] and t["status"] == "dissolved" for t in all_list)


def test_status_transitions_traceable() -> None:
    """状态变更可追溯：open → resolved → dissolved 逐条留痕（5.6）。"""
    cand = _one_candidate()
    r1 = client.post(f"/api/v1/synthesis/tensions/{cand['id']}/status",
                     json={"status": "resolved"}, headers=AUTH)
    assert r1.status_code == 200 and r1.json()["status"] == "resolved"
    r2 = client.post(f"/api/v1/synthesis/tensions/{cand['id']}/status",
                     json={"status": "dissolved"}, headers=AUTH)
    assert r2.status_code == 200
    events = r2.json()["events"]
    assert [(e["from_status"], e["to_status"]) for e in events] == [
        (None, "open"), ("open", "resolved"), ("resolved", "dissolved"),
    ]
    assert all(e["at"] for e in events)


def test_invalid_status_and_kind_rejected() -> None:
    cand = _one_candidate()
    r = client.post(f"/api/v1/synthesis/tensions/{cand['id']}/status",
                    json={"status": "archived"}, headers=AUTH)
    assert r.status_code == 422
    r = client.get("/api/v1/synthesis/tensions", params={"status": "archived"}, headers=AUTH)
    assert r.status_code == 422
    r = client.get("/api/v1/synthesis/tensions", params={"kind": "rumour"}, headers=AUTH)
    assert r.status_code == 422


def test_tension_isolation_between_users() -> None:
    _one_candidate()
    body = client.get("/api/v1/synthesis/tensions", headers=AUTH_BOB).json()
    assert body["results"] == []
    # 跨用户确认/忽略被拒
    mine = client.get("/api/v1/synthesis/tensions", headers=AUTH).json()["candidates"][0]
    r = client.post(f"/api/v1/synthesis/tensions/{mine['id']}/confirm", headers=AUTH_BOB)
    assert r.status_code == 404


def test_detect_tensions_requires_auth() -> None:
    assert client.post("/api/v1/synthesis/detect-tensions").status_code == 401
    assert client.get("/api/v1/synthesis/tensions").status_code == 401
