"""zhesi-atlas-resilience 4.1-4.4 验证：论证结构序列化（全离线）。

- 4.1 argument 字段（claim/premises/support|attack）+ schema 校验；旧卡空论证、散文不变
- 4.2 Argdown 导出（含主张、前提与支持/攻击关系）
- 4.3 Argdown 导入 + 未识别语法报告；往返后立场/理由/最强反驳/回应/现状保留
- 4.4 前提重叠比对（共享前提可被判定为共享）
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fd_zhesi_api.main import app

client = TestClient(app)
AUTH = {"Authorization": "Bearer tok-alice"}
AUTH_BOB = {"Authorization": "Bearer tok-bob"}

QUESTION = "Free will: compatibilism, libertarianism, or no free will?"
POSITION = "compatibilism"


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("FD_ZHESI_DB", str(tmp_path / "personal.db"))
    monkeypatch.setenv("FD_ZHESI_AUTH_DEV_TOKENS", "tok-alice=alice,tok-bob=bob")


def _card(**over) -> dict:
    body = {
        "question": QUESTION,
        "position": POSITION,
        "reasons": "日常经验里我能另作选择",
        "question_ref": "survey-2020:free will",
    }
    body.update(over)
    r = client.post("/api/v1/cards", json=body, headers=AUTH)
    assert r.status_code == 201, r.text
    return r.json()


ARGUMENT = {
    "claim": "相容论成立：自由意志与决定论可以并存",
    "premises": [
        {"id": "P1", "text": "自由意味着不被外在强制"},
        {"id": "P2", "text": "决定论不构成外在强制"},
    ],
    "edges": [
        {"from": "P1", "to": "claim", "type": "support"},
        {"from": "P2", "to": "claim", "type": "support"},
    ],
}


# ------------------------------------------------------------ 4.1 存储与校验 ----
def test_new_card_reads_empty_argument() -> None:
    card = _card()
    assert card["argument"] == {"claim": POSITION, "premises": [], "edges": []}


def test_argument_roundtrip_and_prose_untouched() -> None:
    card = _card()
    r = client.post(f"/api/v1/cards/{card['id']}/argument", json=ARGUMENT, headers=AUTH)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["argument"]["premises"] == ARGUMENT["premises"]
    assert out["argument"]["edges"] == ARGUMENT["edges"]
    # 散文字段不变
    assert out["reasons"] == card["reasons"]
    assert out["position"] == card["position"]
    assert out["strongest_objection"] is None


def test_argument_schema_rejects_bad_premise_id() -> None:
    card = _card()
    bad = {"claim": "x", "premises": [{"id": "1bad", "text": "t"}], "edges": []}
    r = client.post(f"/api/v1/cards/{card['id']}/argument", json=bad, headers=AUTH)
    assert r.status_code == 422
    assert "前提标识" in r.json()["detail"]


def test_argument_schema_rejects_duplicate_premise_ids() -> None:
    card = _card()
    bad = {
        "claim": "x",
        "premises": [{"id": "P1", "text": "a"}, {"id": "P1", "text": "b"}],
        "edges": [],
    }
    r = client.post(f"/api/v1/cards/{card['id']}/argument", json=bad, headers=AUTH)
    assert r.status_code == 422 and "重复" in r.json()["detail"]


def test_argument_schema_rejects_dangling_edge() -> None:
    card = _card()
    bad = {
        "claim": "x",
        "premises": [{"id": "P1", "text": "a"}],
        "edges": [{"from": "P9", "to": "claim", "type": "attack"}],
    }
    r = client.post(f"/api/v1/cards/{card['id']}/argument", json=bad, headers=AUTH)
    assert r.status_code == 422 and "边起点" in r.json()["detail"]


def test_argument_rejects_unknown_edge_type() -> None:
    card = _card()
    bad = {
        "claim": "x",
        "premises": [{"id": "P1", "text": "a"}],
        "edges": [{"from": "P1", "to": "claim", "type": "refute"}],
    }
    r = client.post(f"/api/v1/cards/{card['id']}/argument", json=bad, headers=AUTH)
    assert r.status_code == 422


def test_old_card_without_argument_column_reads_empty(tmp_path) -> None:
    """旧卡（0004 迁移之前落库）以空论证读取，散文字段不变（向后兼容）。"""
    from fd_zhesi_api import personal

    conn = personal.connect()
    personal.migrate(conn)
    cid = personal.new_id()
    ts = personal.now()
    # 直接插一行不带 argument 的卡（模拟旧库行）
    conn.execute(
        "INSERT INTO stance_cards (id, user_id, question, position, reasons, created_at,"
        " updated_at, argument) VALUES (?,?,?,?,?,?,?, NULL)",
        (cid, "alice", QUESTION, POSITION, "旧理由", ts, ts),
    )
    conn.commit()
    card = personal.get_card(conn, "alice", cid)
    conn.close()
    assert card["argument"] == {"claim": POSITION, "premises": [], "edges": []}
    assert card["reasons"] == "旧理由"


# ---------------------------------------------------------------- 4.2 导出 ----
def test_argdown_export_contains_structure() -> None:
    card = _card()
    client.post(f"/api/v1/cards/{card['id']}/argument", json=ARGUMENT, headers=AUTH)
    r = client.get(f"/api/v1/cards/{card['id']}/argdown", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["format"] == "argdown"
    text = body["text"]
    assert f"[stance-{card['id']}]" in text          # 主张
    assert "(P1) 自由意味着不被外在强制" in text      # 前提
    assert "(P1) -> [stance-" in text                 # 支持关系
    assert "fd-zhesi-meta:" in text                   # 散文随行


def test_argdown_export_renders_attack_edge() -> None:
    card = _card()
    argument = {
        "claim": "相容论成立",
        "premises": [{"id": "C1", "text": "后果论证质疑可另作选择"}],
        "edges": [{"from": "C1", "to": "claim", "type": "attack"}],
    }
    client.post(f"/api/v1/cards/{card['id']}/argument", json=argument, headers=AUTH)
    text = client.get(f"/api/v1/cards/{card['id']}/argdown", headers=AUTH).json()["text"]
    assert "(C1) ->< [stance-" in text  # 攻击关系


# ---------------------------------------------------------------- 4.3 导入 ----
def test_argdown_roundtrip_preserves_all_fields() -> None:
    """往返后立场、理由、最强反驳、回应、现状均保留（spec「往返不丢字段」）。"""
    card = _card()
    cid = card["id"]
    client.post(f"/api/v1/cards/{cid}/argument", json=ARGUMENT, headers=AUTH)
    client.post(f"/api/v1/cards/{cid}/objection",
                json={"objection": "后果论证：决定论下无法另作选择"}, headers=AUTH)
    client.post(f"/api/v1/cards/{cid}/response",
                json={"my_response": "以条件式解读「能够」", "stability": "wavering"},
                headers=AUTH)
    source = client.get(f"/api/v1/cards/{cid}", headers=AUTH).json()

    exported = client.get(f"/api/v1/cards/{cid}/argdown", headers=AUTH).json()["text"]
    r = client.post("/api/v1/cards/argdown", json={"text": exported}, headers=AUTH)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["warnings"] == []
    restored = body["card"]

    assert restored["id"] != cid                       # 导入建新卡
    assert restored["question"] == source["question"]
    assert restored["question_ref"] == source["question_ref"]
    assert restored["position"] == source["position"]
    assert restored["reasons"] == source["reasons"]
    assert restored["strongest_objection"] == source["strongest_objection"]
    assert restored["my_response"] == source["my_response"]
    assert restored["stability"] == source["stability"]
    assert restored["argument"] == source["argument"]


def test_argdown_import_reports_unrecognised_syntax() -> None:
    text = (
        "[stance-x]: 主张文本\n\n"
        "(P1) 一个前提\n"
        "(P1) -> [stance-x]\n"
        "~~~ 这是 Argdown 里我们不支持的语法 ~~~\n"
    )
    r = client.post("/api/v1/cards/argdown",
                    json={"text": text, "question": QUESTION, "position": POSITION,
                          "question_ref": "survey-2020:free will"},
                    headers=AUTH)
    assert r.status_code == 201, r.text
    body = r.json()
    assert any("未识别" in w for w in body["warnings"])   # 不静默丢弃
    assert body["card"]["argument"]["premises"] == [{"id": "P1", "text": "一个前提"}]


def test_argdown_import_requires_question_and_position() -> None:
    r = client.post("/api/v1/cards/argdown", json={"text": "[x]: only claim"}, headers=AUTH)
    assert r.status_code == 422


# ---------------------------------------------------------------- 4.4 比对 ----
def test_premise_overlap_detected_between_cards() -> None:
    """两张共享前提的立场卡可被判定为共享（4.4）。"""
    card_a = _card()
    card_b = _card(position="libertarianism")
    shared = {"id": "P1", "text": "自由意味着不被外在强制"}
    client.post(f"/api/v1/cards/{card_a['id']}/argument", headers=AUTH, json={
        "claim": "相容论成立",
        "premises": [shared, {"id": "P2", "text": "决定论不构成外在强制"}],
        "edges": [{"from": "P1", "to": "claim", "type": "support"}],
    })
    client.post(f"/api/v1/cards/{card_b['id']}/argument", headers=AUTH, json={
        "claim": "只有非决定论才有自由",
        "premises": [shared, {"id": "Q9", "text": "真正的自由要求另作选择的可能"}],
        "edges": [{"from": "Q9", "to": "claim", "type": "support"}],
    })

    r = client.get("/api/v1/cards/compare",
                   params={"a": card_a["id"], "b": card_b["id"]}, headers=AUTH)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["shares_premises"] is True
    assert body["shared_by_id"] == ["P1"]
    assert body["conclusions_opposed"] is True          # 同一问题的相反表态
    assert any("P1" in label for label in body["shared_premises"])


def test_premise_overlap_detected_by_text_when_ids_differ() -> None:
    """标识不同但文本相同也算共享（归一化后比对）。"""
    card_a = _card()
    card_b = _card(position="libertarianism")
    for card, pid in ((card_a, "A1"), (card_b, "B7")):
        client.post(f"/api/v1/cards/{card['id']}/argument", headers=AUTH, json={
            "claim": "c",
            "premises": [{"id": pid, "text": "  自由   意味着不被外在强制。"}],
            "edges": [],
        })
    body = client.get("/api/v1/cards/compare",
                      params={"a": card_a["id"], "b": card_b["id"]},
                      headers=AUTH).json()
    assert body["shared_by_id"] == []
    assert body["shared_by_text"] == ["A1"]
    assert body["shares_premises"] is True


def test_compare_rejects_other_users_cards() -> None:
    card_a = _card()
    r = client.get("/api/v1/cards/compare",
                   params={"a": card_a["id"], "b": card_a["id"]}, headers=AUTH_BOB)
    assert r.status_code == 404


def test_no_overlap_when_premises_differ() -> None:
    card_a = _card()
    card_b = _card(position="libertarianism")
    client.post(f"/api/v1/cards/{card_a['id']}/argument", headers=AUTH, json={
        "claim": "c", "premises": [{"id": "P1", "text": "甲"}], "edges": []})
    client.post(f"/api/v1/cards/{card_b['id']}/argument", headers=AUTH, json={
        "claim": "d", "premises": [{"id": "P1", "text": "乙"}], "edges": []})
    body = client.get("/api/v1/cards/compare",
                      params={"a": card_a["id"], "b": card_b["id"]},
                      headers=AUTH).json()
    # 标识相同但文本不同：不算共享（宁缺毋滥；标识只是卡内局部编号）
    assert body["shared_by_id"] == ["P1"]
    assert body["shared_by_text"] == []
    assert body["shares_premises"] is False
