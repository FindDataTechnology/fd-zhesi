"""zhesi-atlas-resilience 5.1-5.3 验证：steel-manning（全离线）。

- 5.1 候选生成与强度排序（覆盖前提数、参照系支持度、来源权威度）；弱候选不入选
- 5.2 参照系上界校验：同一对立立场存在更强论证时拒绝当前候选
- 5.3 分歧点输出（共享前提、真正分歧、反驳成立条件）可逐项核对
"""

from __future__ import annotations

import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fd_zhesi_api import cards, loops, personal
from fd_zhesi_api.loops import (
    MIN_STRENGTH,
    STEELMAN_WEIGHTS,
    SteelmanCandidate,
    check_upper_bound,
    disagreement_points,
    generate_steelman_candidates,
    select_strongest,
)

app = FastAPI()
app.include_router(cards.router)
app.include_router(loops.router)
client = TestClient(app)
AUTH = {"Authorization": "Bearer dev-tok-alice"}

FW_Q = "Free will: compatibilism, libertarianism, or no free will?"

_STANCES = [
    ("2020", FW_Q, "compatibilism", "相容论（自由意志与决定论可以并存）", 59.2),
    ("2020", FW_Q, "libertarianism", "自由意志论（人有非决定论的自由）", 18.8),
    ("2020", FW_Q, "no free will", "无自由意志（决定论成立）", 11.2),
]
_CONCEPTS = [
    ("free will", "Free Will", "https://plato.stanford.edu/entries/freewill/", "freewill snippet"),
    ("compatibilism", "Compatibilism", "https://plato.stanford.edu/entries/compatibilism/", "compat"),
    ("determinism", "Causal Determinism", "https://plato.stanford.edu/entries/determinism-causal/", "det"),
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
    for t, title, url, snip in _CONCEPTS:
        conn.execute(
            "INSERT INTO concepts (term, title, url, snippet, retrieved_at) VALUES (?,?,?,?,?)",
            (t, title, url, snip, "2026-01-01"),
        )
    conn.commit()
    conn.close()


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    ref = tmp_path / "reference.db"
    _make_ref_db(ref)
    monkeypatch.setenv("FD_ZHESI_REF_DB", str(ref))
    monkeypatch.setenv("FD_ZHESI_DB", str(tmp_path / "personal.db"))
    monkeypatch.setenv("FD_ZHESI_AUTH_DEV_TOKENS", "dev-tok-alice=alice")
    monkeypatch.delenv("FD_ZHESI_LLM_API_KEY", raising=False)


def _card_with_argument() -> str:
    r = client.post("/api/v1/cards", json={
        "question": FW_Q, "position": "compatibilism",
        "reasons": "日常经验", "question_ref": "survey-2020:free will",
    }, headers=AUTH)
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    r = client.post(f"/api/v1/cards/{cid}/argument", json={
        "claim": "相容论成立",
        "premises": [
            {"id": "P1", "text": "道德责任需要行动者能对后果负责"},
            {"id": "P2", "text": "determinism 并不等于外在强制"},
        ],
        "edges": [{"from": "P2", "to": "claim", "type": "support"}],
    }, headers=AUTH)
    assert r.status_code == 200, r.text
    return cid


def _debate(card_id: str) -> dict:
    r = client.post("/api/v1/debate/strongest-objection",
                    json={"card_id": card_id}, headers=AUTH)
    assert r.status_code == 200, r.text
    return r.json()


def _cand(option: str, variant: str, strength: float, **kw) -> SteelmanCandidate:
    return SteelmanCandidate(
        option=option, variant=variant, evidence=kw.get("evidence", []),
        covered_premises=kw.get("covered_premises", []),
        coverage_ratio=kw.get("coverage_ratio", 0.0),
        authority=kw.get("authority", 0.8),
        reference_support=kw.get("reference_support", 0.1),
        strength=strength,
    )


# --------------------------------------------------- 5.1 候选生成与强度排序 ----
def test_candidate_generation_covers_premises() -> None:
    card = {"question": FW_Q, "position": "compatibilism", "argument": {
        "claim": "c",
        "premises": [
            {"id": "P1", "text": "道德责任需要行动者能对后果负责"},
            {"id": "P2", "text": "determinism 并不等于外在强制"},
        ],
        "edges": [],
    }}
    dist = {"survey_round": "2020", "question": FW_Q}
    opposing = [
        {"option": "libertarianism", "option_zh": "自由意志论", "pct": 18.8},
        {"option": "no free will", "option_zh": "无自由意志", "pct": 11.2},
    ]
    sep_cards = [{"title": "Free Will", "url": "https://x/freewill/", "snippet": "determinism"}]
    cands = generate_steelman_candidates(card, dist, opposing, sep_cards, [])

    assert {c.option for c in cands} == {"libertarianism", "no free will"}
    # 有 SEP 时每个选项都有 survey-only 与 survey+sep 两档
    assert {c.variant for c in cands} == {"survey-only", "survey+sep"}
    # 词面覆盖：P2 含 determinism，与 SEP 片段重叠 → 至少被一档覆盖
    assert any("P2" in c.covered_premises for c in cands)
    # 排序：强度降序
    strengths = [c.strength for c in cands]
    assert strengths == sorted(strengths, reverse=True)
    # 权威度：SEP 档高于 survey-only 档（同一选项）
    by_variant = {(c.option, c.variant): c for c in cands}
    assert by_variant[("libertarianism", "survey+sep")].authority > \
        by_variant[("libertarianism", "survey-only")].authority
    assert STEELMAN_WEIGHTS == {"coverage": 0.4, "authority": 0.4, "support": 0.2}


def test_weak_candidate_excluded() -> None:
    """弱候选不入选：强度低于门槛的候选被挡下并给出原因（5.1）。"""
    strong = _cand("atheism", "survey+sep", 0.55)
    weak = _cand("atheism", "atlas-only", MIN_STRENGTH - 0.05)
    best, rejected = select_strongest([strong, weak])
    assert best is strong
    assert len(rejected) == 1
    assert rejected[0]["variant"] == "atlas-only"
    assert rejected[0]["reason"].startswith("below_min_strength")


def test_only_weak_candidates_returns_none() -> None:
    best, rejected = select_strongest([_cand("x", "v", 0.1), _cand("y", "v", 0.2)])
    assert best is None and len(rejected) == 2


# ------------------------------------------------------- 5.2 参照系上界校验 ----
def test_upper_bound_rejects_weaker_same_option() -> None:
    """同一对立立场存在更强论证 → 拒绝当前候选（5.2，构造样例）。"""
    weak = _cand("libertarianism", "survey-only", 0.34)
    strong = _cand("libertarianism", "survey+sep", 0.52)
    ok, reason = check_upper_bound(weak, [weak, strong])
    assert ok is False
    assert reason.startswith("weaker_than_reference")
    assert "0.52" in reason and "0.34" in reason

    ok_strong, reason_strong = check_upper_bound(strong, [weak, strong])
    assert ok_strong is True and reason_strong is None


def test_upper_bound_ignores_other_options() -> None:
    """别的对立立场更强不影响本候选（上界只在同一立场内比较）。"""
    cand = _cand("libertarianism", "survey+sep", 0.4)
    other = _cand("no free will", "survey+sep", 0.9)
    ok, reason = check_upper_bound(cand, [cand, other])
    assert ok is True and reason is None


def test_select_strongest_applies_upper_bound() -> None:
    weak = _cand("libertarianism", "survey-only", 0.34)
    strong = _cand("libertarianism", "survey+sep", 0.52)
    best, rejected = select_strongest([weak, strong])
    assert best is strong
    assert any(r["reason"].startswith("weaker_than_reference") for r in rejected)


def test_endpoint_reports_steelman_selection() -> None:
    cid = _card_with_argument()
    out = _debate(cid)
    steelman = out["steelman"]
    assert steelman["min_strength"] == MIN_STRENGTH
    assert steelman["weights"] == STEELMAN_WEIGHTS
    selected = steelman["selected"]
    assert selected["strength"] >= MIN_STRENGTH
    assert selected["coverage_proxy"] == "lexical-overlap"  # 不冒充语义判断
    # 上界成立：同一选项里没有比 selected 更强的候选仍在被选中之外
    same_option_stronger = [
        r for r in steelman["rejected"]
        if r["option"] == selected["option"] and r["strength"] > selected["strength"]
    ]
    assert same_option_stronger == []
    # 选定选项就是模板渲染的选项（不是简单按 pct 取第一）
    assert selected["option"] in out["objection"]


# --------------------------------------------------------------- 5.3 分歧点 ----
def test_disagreement_points_three_parts() -> None:
    """输出含共享前提、真正分歧、反驳成立条件三项且可逐项核对（5.3）。"""
    card = {
        "question": FW_Q,
        "position": "compatibilism",
        "question_ref": "survey-2020:free will",
        "argument": {
            "claim": "相容论成立",
            "premises": [
                {"id": "P1", "text": "道德责任需要行动者能对后果负责"},
                {"id": "P2", "text": "determinism 并不等于外在强制"},
            ],
            "edges": [],
        },
    }
    dist = {"survey_round": "2020", "question": FW_Q}
    opposing = [{"option": "libertarianism", "option_zh": "自由意志论", "pct": 18.8}]
    sep_cards = [{"title": "Free Will", "url": "https://x/fw/", "snippet": "determinism"}]
    cands = generate_steelman_candidates(card, dist, opposing, sep_cards, [])
    best, _ = select_strongest(cands)
    assert best is not None

    points = disagreement_points(card, best)
    # 三项都在
    assert set(points) >= {"shared_premises", "real_disagreement", "conditions"}
    # 覆盖到的前提进 contested，未覆盖的进 shared（可逐项核对；两者都是前提文本）
    assert "determinism 并不等于外在强制" in points["contested_premises"]
    assert "道德责任需要行动者能对后果负责" in points["shared_premises"]
    assert "道德责任需要行动者能对后果负责" not in points["contested_premises"]
    # 真正分歧：落在六轴的具体差异上
    assert points["real_disagreement"]
    assert any("决定与自由" in item for item in points["real_disagreement"])
    # 成立条件与分歧一一对应
    assert len(points["conditions"]) == len(points["real_disagreement"])
    assert "note" in points


def test_endpoint_returns_disagreement_points() -> None:
    cid = _card_with_argument()
    out = _debate(cid)
    points = out["disagreement_points"]
    assert "shared_premises" in points
    assert "real_disagreement" in points
    assert "conditions" in points
    assert points["real_disagreement"], "自由意志题在决定轴上必有分歧"
    assert all("若在" in c for c in points["conditions"])


def test_debate_still_persists_objection_and_citations() -> None:
    """回归：steel-manning 改造后仍回写立场卡、引用仍全部可解析。"""
    cid = _card_with_argument()
    out = _debate(cid)
    assert out["citations"]
    assert out["engine"] == "deterministic"
    conn = personal.connect()
    personal.migrate(conn)
    card = personal.get_card(conn, "alice", cid)
    conn.close()
    assert card["strongest_objection"] == out["objection"]
    assert card["argument"]["premises"], "论证结构不因辩闭环被覆盖"
