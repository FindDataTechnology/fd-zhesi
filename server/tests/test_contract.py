"""task 5.1 契约测试：授权边界、字段完整性、向后兼容（新增字段不破坏 v1 消费方）。"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from fd_zhesi_api.main import app

client = TestClient(app)
AUTH = {"Authorization": "Bearer dev-tok-alice"}


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("FD_ZHESI_DB", str(tmp_path / "personal.db"))
    monkeypatch.setenv("FD_ZHESI_AUTH_DEV_TOKENS", "dev-tok-alice=alice")


def _seed_card():
    r = client.post("/api/v1/cards", json={
        "question": "free will", "position": "compatibilism",
        "reasons": "日常经验", "question_ref": "survey-2020:free will",
    }, headers=AUTH)
    assert r.status_code == 201
    return r.json()


def test_denied_without_grant() -> None:
    _seed_card()
    r = client.get("/api/v1/contract/cards", params={"consumer": "juchuang"}, headers=AUTH)
    assert r.status_code == 403  # 未授权：剧创取不到（spec 授权边界继承）


def test_grant_scoped_delivery() -> None:
    card = _seed_card()
    r = client.post("/api/v1/grants", json={"consumer": "juchuang", "card_kinds": ["stance"]},
                    headers=AUTH)
    assert r.status_code == 201

    r = client.get("/api/v1/contract/cards", params={"consumer": "juchuang"}, headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["contract_version"] == "2"
    assert body["consumer"] == "juchuang"
    assert len(body["cards"]) == 1
    c = body["cards"][0]
    # 契约字段集完整性：v1 字段一个不少，v2 新增 argument 可选字段在场
    v1_fields = {"id", "question", "question_ref", "position",
                 "stability", "strongest_objection", "as_of"}
    assert set(c) >= v1_fields and "argument" in set(c)
    # 新增字段可选：旧卡（未填论证）以空论证形态下发，散文字段不受影响
    assert c["argument"] == {"claim": "compatibilism", "premises": [], "edges": []}
    assert c["id"] == card["id"] and c["position"] == "compatibilism"
    # 张力未授权 → 不下发张力数据
    assert body["tensions"] == []

    # 开放 tension 后（空张力簿）字段仍在
    client.post("/api/v1/grants", json={"consumer": "juchuang", "card_kinds": ["stance", "tension"]},
                headers=AUTH)
    body2 = client.get("/api/v1/contract/cards", params={"consumer": "juchuang"},
                       headers=AUTH).json()
    assert "tensions" in body2 and body2["contract_version"] == "2"


def test_backward_compat_additive_only() -> None:
    """契约演进只增字段：模拟 v1 消费方按旧字段集取子集，不受新增字段影响。"""
    _seed_card()
    client.post("/api/v1/grants", json={"consumer": "juchuang", "card_kinds": ["stance"]},
                headers=AUTH)
    body = client.get("/api/v1/contract/cards", params={"consumer": "juchuang"}, headers=AUTH).json()
    v1_fields = {"id", "question", "question_ref", "position",
                 "stability", "strongest_objection", "as_of"}
    for c in body["cards"]:
        consumed = {k: c[k] for k in v1_fields}  # 旧消费方按已知字段取子集
        assert consumed["position"]
    assert set(body["cards"][0]) >= v1_fields  # 新字段只能是超集


def test_grant_validation() -> None:
    r = client.post("/api/v1/grants", json={"consumer": "juchuang", "card_kinds": ["secret"]},
                    headers=AUTH)
    assert r.status_code == 422


def test_v2_tension_fields_are_additive() -> None:
    """v2 契约的张力新增 kind/tension_type/status，且 v1 字段一个不少（6.3）。"""
    from fd_zhesi_api import personal, synthesis

    _seed_card()
    conn = personal.connect()
    personal.migrate(conn)
    tid = personal.new_id()
    ts = personal.now()
    conn.execute(
        "INSERT INTO tensions (id, user_id, card_ids, description, source, status,"
        " created_at, kind, tension_type) VALUES (?,?,?,?,?,'open',?, 'candidate',"
        " 'value-conflict')",
        (tid, "alice", json.dumps(["c1", "c2"]), "d", "s", ts),
    )
    conn.commit()
    conn.close()

    client.post("/api/v1/grants", json={"consumer": "juchuang",
                                        "card_kinds": ["stance", "tension"]}, headers=AUTH)
    body = client.get("/api/v1/contract/cards", params={"consumer": "juchuang"},
                      headers=AUTH).json()
    assert body["contract_version"] == "2"
    assert len(body["tensions"]) == 1
    t = body["tensions"][0]
    # v1 字段仍在
    assert set(t) >= {"id", "card_ids", "description", "source"}
    # v2 新增字段在场且取合法值
    assert t["kind"] == "candidate"
    assert t["tension_type"] == "value-conflict"
    assert t["status"] == "open"
    assert t["tension_type"] in personal.TENSION_TYPES
    # 旧消费方按 v1 字段取子集照常工作
    v1_subset = {k: t[k] for k in ("id", "card_ids", "description", "source")}
    assert v1_subset["description"] == "d"
