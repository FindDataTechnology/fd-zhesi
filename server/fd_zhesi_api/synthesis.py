"""谱闭环 + 张力簿 API（task 4.3 / 4.4；zhesi-atlas-resilience 2.x / 5.4-5.6）。

谱闭环：active 立场卡经 axis_map 归一为六轴增量，求和合成投影，并到参照系
哲学家中找最近思想邻居；每次合成都是新版本、历史全保留（思想年轮的投影面，
spec「重合成保留历史」）。

**降级（2.1/2.2）**：参照系四层（atlas / wikidata / survey / sep）由
`axis_map.detect_missing_layers` 探测。Atlas 缺失时投影照常产出（增量来自
确定性 curated 表，绝不推测坐标），但邻居改用手工种子层锚定，输出带
`degraded` / `confidence` / `missing_layers` / `reasons`，并随投影存档——
界面据此标注「为什么置信度下降」。Atlas 恢复后重新摄取即用全量重合成（2.3）。

**张力簿（5.4-5.6）**：既成张力来自 curated 张力对表（宁缺毋滥）；候选张力由
「前提重叠 + 结论相反」或「影响图 critical 关系 + 双方立场卡」推断，标
`kind=candidate` 并附推断依据，与既成分离展示，用户可确认或忽略，状态流转留痕。

投影语义（与 design D4「与种子数据同空间」对齐）：参照系哲学家六轴取值
0-10，故用户投影也锚定在同一 0-10 空间——各轴符号增量求和（clamp 到
[-10,10]）后加中性锚点 5.0，再 clamp 到 [0,10]，与哲学家邻居可直接算
欧氏距离。轴表版本随 axis_map.AXES_VERSION 存档，改表不破坏历史投影。

数据归属：投影与张力只落个人层自有库（personal，物理分库铁律）；参照系
库只读（仅 SELECT，绝不写）。
"""

from __future__ import annotations

import json
import math
import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import personal, seed_axes
from .argument import premise_overlap
from .auth import require_user
from .axis_map import (
    AXES,
    AXES_VERSION,
    degradation,
    detect_missing_layers,
    resolve,
    resolve_question,
)
from .tension_map import candidate_type, lookup_tension

router = APIRouter(prefix="/api/v1/synthesis", tags=["synthesis"])

SYNTHESIS_THRESHOLD = 5  # spec「立场积累达到合成阈值」：active 且可映射的卡各 ≥5
NEIGHBOR_COUNT = 8
NEUTRAL_ANCHOR = 5.0  # Atlas 六轴空间（0-10）的中点：无立场的中立位置


# ---- 领域逻辑（纯函数，测试直调） ----

def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def compute_axes(deltas_list: list[dict[str, float]]) -> dict[str, float]:
    """多张卡的轴增量 → 六轴投影（0-10 空间，见模块 docstring 的锚定语义）。"""
    axes: dict[str, float] = {}
    for axis in AXES:
        signed_sum = _clamp(sum(d.get(axis, 0.0) for d in deltas_list), -10.0, 10.0)
        axes[axis] = round(_clamp(NEUTRAL_ANCHOR + signed_sum, 0.0, 10.0), 2)
    return axes


def neighbors_from_rows(
    axes: dict[str, float], rows: list, limit: int = NEIGHBOR_COUNT,
) -> list[dict]:
    """六轴欧氏距离取最近思想邻居（rows 需含 atlas_id/name_en/name_zh/六轴）。"""
    scored = []
    for r in rows:
        get = (lambda k: r[k]) if isinstance(r, sqlite3.Row) else (lambda k: r.get(k))
        coords = [get(a) for a in AXES]
        if any(c is None for c in coords):
            continue  # 轴不完整的哲学家不参与（诚实：不臆造缺省值）
        dist = math.sqrt(sum((axes[a] - c) ** 2 for a, c in zip(AXES, coords)))
        scored.append({
            "atlas_id": get("atlas_id"),
            # Wikidata 回填缺名时回退 Atlas 原生 pt 名，不显示 NULL
            "name_en": get("name_en") or get("name_pt") or get("name_en"),
            "name_zh": get("name_zh") or get("name_pt") or get("name_en"),
            "distance": round(dist, 4),
        })
    scored.sort(key=lambda n: (n["distance"], n["atlas_id"]))
    return scored[:limit]


def nearest_neighbors(
    axes: dict[str, float], ref_conn: sqlite3.Connection, limit: int = NEIGHBOR_COUNT,
) -> list[dict]:
    """参照系哲学家里按六轴欧氏距离取最近思想邻居（参照系只读）。"""
    rows = ref_conn.execute(
        "SELECT atlas_id, name_pt, name_en, name_zh,"
        " individualism, materialism, rationalism, determinism, transcendence,"
        " universalism FROM philosophers"
    ).fetchall()
    return neighbors_from_rows(axes, rows, limit)


def _reference_conn() -> sqlite3.Connection | None:
    """打开参照系库（只读用途）。库打不开 → 明确 503；能打开但为空 → 降级。

    与 2.1 之前的行为差别：**表空不再 503**，而是返回连接由调用方探测缺失层并
    走降级路径（spec「Atlas 缺失时谱闭环降级」）。只有「参照系包不可用」或
    「SQLite 打不开」才是硬错误——那时连缺失层都无从判断。
    """
    try:
        from fd_zhesi_reference.config import Settings
    except ImportError as exc:  # pragma: no cover —— 环境缺包
        raise HTTPException(503, f"参照系服务包不可用: {exc}") from exc
    try:
        return Settings.from_env().connect()
    except sqlite3.Error as exc:
        raise HTTPException(503, f"参照系库不可用: {exc}") from exc


def _db() -> sqlite3.Connection:
    conn = personal.connect()
    personal.migrate(conn)
    return conn


def _resolve_cards(cards: list[dict]) -> tuple[list[tuple[dict, object]], list[dict]]:
    """active 卡分成（可映射卡, 归一结果）与 skipped（诚实列出映射不上的）。"""
    resolved: list[tuple[dict, object]] = []
    skipped: list[dict] = []
    for card in cards:
        r = resolve(card["question"], card["position"], card.get("question_ref"))
        if r is None:
            key = resolve_question(card["question"], card.get("question_ref"))
            reason = "position_not_mapped" if key else "question_not_mapped"
            skipped.append({
                "card_id": card["id"], "question": card["question"],
                "position": card["position"], "reason": reason,
            })
        else:
            resolved.append((card, r))
    return resolved, skipped


# ---- 谱闭环：投影与思想邻居（4.3 + 2.1/2.2 降级） ----

@router.post("/project", status_code=201)
def project(user_id: str = Depends(require_user)) -> dict:
    """合成六轴投影 + 最近 8 位思想邻居；每次调用产生新版本，历史保留。

    Atlas 缺失时走降级路径：投影照常产出，邻居来自手工种子层，
    输出带 degraded/confidence/missing_layers/reasons（并随投影存档）。
    """
    conn = _db()
    try:
        cards = personal.list_cards(conn, user_id, "active")
        if len(cards) < SYNTHESIS_THRESHOLD:
            raise HTTPException(
                412,
                f"active 立场卡 {len(cards)} 张，不足合成阈值 {SYNTHESIS_THRESHOLD} 张；"
                "继续表态积累后再合成",
            )
        resolved, skipped = _resolve_cards(cards)
        if len(resolved) < SYNTHESIS_THRESHOLD:
            raise HTTPException(
                412,
                f"active 立场卡 {len(cards)} 张，但可映射到六轴的仅 {len(resolved)} 张"
                f"（不足 {SYNTHESIS_THRESHOLD}）；请在经典立场问题上继续表态后再合成",
            )
        axes = compute_axes([r.deltas for _, r in resolved])

        ref = _reference_conn()
        try:
            missing_layers = detect_missing_layers(ref)
            if "atlas" in missing_layers:
                # 降级：手工种子层锚定邻居（真实 Atlas 子集，不是推测坐标）
                neighbors = neighbors_from_rows(axes, seed_axes.seed_rows())
                neighbor_layer = "manual-seed"
            else:
                neighbors = nearest_neighbors(axes, ref)
                neighbor_layer = "atlas"
        finally:
            ref.close()

        info = degradation(missing_layers)
        pid = personal.new_id()
        ts = personal.now()
        conn.execute(
            "INSERT INTO projections (id, user_id, axes_version, axes, neighbors,"
            " based_on_cards, created_at, missing_layers, confidence)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (
                pid, user_id, AXES_VERSION,
                json.dumps(axes, ensure_ascii=False),
                json.dumps(neighbors, ensure_ascii=False),
                json.dumps([card["id"] for card, _ in resolved]),
                ts,
                json.dumps(info["missing_layers"], ensure_ascii=False),
                info["confidence"],
            ),
        )
        conn.commit()
        personal.audit(conn, user_id, "synthesis.project", pid, "allowed",
                       detail=(f"mappable={len(resolved)}, skipped={len(skipped)},"
                               f" confidence={info['confidence']},"
                               f" missing={','.join(info['missing_layers']) or '-'}"))
        return {
            "id": pid,
            "axes_version": AXES_VERSION,
            "axes": axes,
            "neighbors": neighbors,
            "neighbor_layer": neighbor_layer,
            "based_on_cards": [card["id"] for card, _ in resolved],
            "active_count": len(cards),
            "mappable_count": len(resolved),
            "skipped": skipped,
            "degraded": info["degraded"],
            "confidence": info["confidence"],
            "missing_layers": info["missing_layers"],
            "degradation_reasons": info["reasons"],
            "created_at": ts,
        }
    finally:
        conn.close()


def _projection_row(r: sqlite3.Row) -> dict:
    def _col(name, default=None):
        try:
            return r[name]
        except (IndexError, KeyError):
            return default

    missing_raw = _col("missing_layers")
    try:
        missing = json.loads(missing_raw) if missing_raw else []
    except (TypeError, ValueError):
        missing = []
    confidence = _col("confidence")
    info = degradation(missing)
    return {
        "id": r["id"],
        "axes_version": r["axes_version"],
        "axes": json.loads(r["axes"]),
        "neighbors": json.loads(r["neighbors"]),
        "based_on_cards": json.loads(r["based_on_cards"]),
        "created_at": r["created_at"],
        "degraded": info["degraded"],
        # 旧投影（0004 之前）无置信度列：按缺失层重算，保持口径一致
        "confidence": confidence if confidence is not None else info["confidence"],
        "missing_layers": missing,
    }


@router.get("/projections")
def list_projections(user_id: str = Depends(require_user)) -> dict:
    """历史投影版本列表，最新在前（重合成保留历史，可对比变迁）。"""
    conn = _db()
    try:
        rows = conn.execute(
            "SELECT * FROM projections WHERE user_id=?"
            " ORDER BY rowid DESC",  # rowid=插入序 → 严格最新在前（时间戳同微秒也不乱序）
            (user_id,),
        ).fetchall()
        return {"results": [_projection_row(r) for r in rows]}
    finally:
        conn.close()


# ---- 张力簿：一致性检测（4.4 + 5.4-5.6） ----

def _tension_row(r: sqlite3.Row) -> dict:
    return personal.tension_row_to_dict(r)


def _tension_dedupe_key(card_ids: list[str], description: str) -> tuple:
    return (frozenset(card_ids), description)


@router.post("/detect-tensions")
def detect_tensions(user_id: str = Depends(require_user)) -> dict:
    """扫 active 卡：curated 张力对 → 既成张力；前提重叠/critical 边 → 候选。

    既成与候选分开返回（spec「候选不冒充既成张力」），重复检测不重复写。
    """
    conn = _db()
    try:
        cards = personal.list_cards(conn, user_id, "active")
        resolved, _skipped = _resolve_cards(cards)
        existing = conn.execute(
            "SELECT card_ids, description FROM tensions WHERE user_id=?",
            (user_id,),
        ).fetchall()
        seen = {_tension_dedupe_key(json.loads(r["card_ids"]), r["description"])
                for r in existing}

        created: list[dict] = []
        candidates: list[dict] = []

        # ---- 既成张力：curated 表命中 ----
        for i in range(len(resolved)):
            for j in range(i + 1, len(resolved)):
                card_a, ra = resolved[i]
                card_b, rb = resolved[j]
                entry = lookup_tension(ra.question_key, ra.position,
                                       rb.question_key, rb.position)
                if not entry:
                    continue  # 宁缺毋滥：无已知张力不生成记录
                card_ids = sorted([card_a["id"], card_b["id"]])
                key = _tension_dedupe_key(card_ids, entry["description"])
                if key in seen:
                    continue
                seen.add(key)
                created.append(
                    _insert_tension(
                        conn, user_id, card_ids, entry["description"], entry["source"],
                        kind="confirmed", tension_type=entry.get("type", "contradiction"),
                        basis=None,
                    )
                )

        # ---- 候选张力：前提重叠 + 结论相反；或 critical 边 + 双方立场卡 ----
        for cand in discover_tension_candidates(conn, user_id, cards):
            key = _tension_dedupe_key(cand["card_ids"], cand["description"])
            if key in seen:
                continue
            seen.add(key)
            candidates.append(
                _insert_tension(
                    conn, user_id, cand["card_ids"], cand["description"],
                    cand["source"], kind="candidate",
                    tension_type=cand["tension_type"], basis=cand["basis"],
                )
            )

        open_count = conn.execute(
            "SELECT COUNT(*) FROM tensions WHERE user_id=? AND status='open'",
            (user_id,),
        ).fetchone()[0]
        if created or candidates:
            personal.audit(conn, user_id, "synthesis.detect_tensions",
                           user_id, "allowed",
                           detail=f"confirmed={len(created)}, candidates={len(candidates)}")
        return {
            "created": created,
            "candidates": candidates,
            "open_count": open_count,
            "checked_pairs": len(resolved) * (len(resolved) - 1) // 2,
        }
    finally:
        conn.close()


def _insert_tension(
    conn, user_id: str, card_ids: list[str], description: str, source: str | None,
    *, kind: str, tension_type: str, basis: dict | None,
) -> dict:
    tid = personal.new_id()
    ts = personal.now()
    conn.execute(
        "INSERT INTO tensions (id, user_id, card_ids, description, source, status,"
        " created_at, kind, basis, tension_type) VALUES (?,?,?,?,?,'open',?,?,?,?)",
        (
            tid, user_id, json.dumps(card_ids), description, source, ts,
            kind, json.dumps(basis, ensure_ascii=False) if basis else None,
            tension_type,
        ),
    )
    conn.commit()
    personal.record_tension_event(conn, user_id, tid, None, "open",
                                  detail=f"kind={kind}")
    row = conn.execute("SELECT * FROM tensions WHERE id=?", (tid,)).fetchone()
    return _tension_row(row)


def discover_tension_candidates(
    conn: sqlite3.Connection, user_id: str, cards: list[dict],
) -> list[dict]:
    """候选张力发现（5.4）：两条推断路径，都带可核对的推断依据。

    路径一（前提重叠 + 结论相反）：两张立场卡共享至少一个前提标识且结论方向相反。
    路径二（影响图 critical 关系）：两张卡引用的人物在影响图中存在 critical 边，
    且双方立场卡都指向该人物代表的立场。

    候选不是断言：`kind=candidate` + `basis` 说明「凭什么怀疑这里有张力」。
    """
    out: list[dict] = []
    by_id = {c["id"]: c for c in cards}

    # 路径一：前提重叠
    for i in range(len(cards)):
        for j in range(i + 1, len(cards)):
            a, b = cards[i], cards[j]
            overlap = premise_overlap(a, b)
            if not overlap["shared"]:
                continue
            ra = resolve(a["question"], a["position"], a.get("question_ref"))
            rb = resolve(b["question"], b["position"], b.get("question_ref"))
            opposed = bool(
                ra and rb and ra.question_key == rb.question_key
                and ra.position != rb.position
            )
            if not opposed:
                continue
            card_ids = sorted([a["id"], b["id"]])
            out.append({
                "card_ids": card_ids,
                "description": (
                    f"两张立场卡共享前提（{', '.join(overlap['shared'])}）"
                    f"但结论相反（{a['position']} vs {b['position']}）"
                ),
                "source": "推断: 前提重叠 + 结论相反",
                "tension_type": candidate_type(overlap=overlap["shared"], opposed=True),
                "basis": {
                    "kind": "premise-overlap",
                    "shared_premises": overlap["shared"],
                    "positions": [a["position"], b["position"]],
                    "questions": [a["question"], b["question"]],
                },
            })

    # 路径二：影响图 critical 关系（参照系有全量图时用图，否则用种子层）
    edges = _critical_edges_for_cards(conn)
    if edges:
        for i in range(len(cards)):
            for j in range(i + 1, len(cards)):
                a, b = cards[i], cards[j]
                hit = _critical_link(a, b, edges)
                if not hit:
                    continue
                card_ids = sorted([a["id"], b["id"]])
                out.append({
                    "card_ids": card_ids,
                    "description": (
                        f"两人物在影响图中为批判关系（{hit['source_name']} → "
                        f"{hit['target_name']}，weight {hit['weight']}），"
                        "而用户对双方立场均有表态"
                    ),
                    "source": "推断: 影响图 critical 关系",
                    "tension_type": candidate_type(overlap=[], opposed=False),
                    "basis": {
                        "kind": "critical-relation",
                        "edge": hit,
                        "positions": [a["position"], b["position"]],
                    },
                })
    return out


def _critical_edges_for_cards(conn: sqlite3.Connection) -> list[dict]:
    """取影响图 critical 边；参照系无图时退回种子层（降级仍可推断）。"""
    try:
        rows = conn.execute(
            "SELECT r.source_id, r.target_id, r.weight,"
            " s.name_en AS source_name, t.name_en AS target_name,"
            " s.name_zh AS source_name_zh, t.name_zh AS target_name_zh"
            " FROM relations r"
            " JOIN philosophers s ON r.source_id = s.atlas_id"
            " JOIN philosophers t ON r.target_id = t.atlas_id"
            " WHERE r.polarity='critical'"
        ).fetchall()
    except sqlite3.Error:
        rows = []
    if rows:
        return [
            {
                "source_id": r["source_id"], "target_id": r["target_id"],
                "weight": r["weight"], "source_name": r["source_name"],
                "target_name": r["target_name"],
                "source_name_zh": r["source_name_zh"],
                "target_name_zh": r["target_name_zh"],
            }
            for r in rows
        ]
    return seed_axes.seed_critical_edges()


_CARD_TEXT_FIELDS = ("question", "question_ref", "position", "reasons")


def _card_text(card: dict) -> str:
    return " ".join(str(card.get(k) or "") for k in _CARD_TEXT_FIELDS).casefold()


def _name_hit(name: str | None, text: str) -> bool:
    """人物名是否被卡片文本引用：全名命中，或名字末段（≥3 字符）命中。"""
    n = (name or "").casefold().strip()
    if not n or not text:
        return False
    if n in text:
        return True
    last = n.split()[-1]
    return len(last) >= 3 and last in text


def _critical_link(card_a: dict, card_b: dict, edges: list[dict]) -> dict | None:
    """两卡是否各自引用了同一条 critical 边的两端（任一端配任一卡）。"""
    text_a, text_b = _card_text(card_a), _card_text(card_b)
    for edge in edges:
        for src_en, src_zh, tgt_en, tgt_zh in (
            (edge.get("source_name"), edge.get("source_name_zh"),
             edge.get("target_name"), edge.get("target_name_zh")),
            (edge.get("target_name"), edge.get("target_name_zh"),
             edge.get("source_name"), edge.get("source_name_zh")),
        ):
            src_hit_a = _name_hit(src_en, text_a) or _name_hit(src_zh, text_a)
            tgt_hit_b = _name_hit(tgt_en, text_b) or _name_hit(tgt_zh, text_b)
            if src_hit_a and tgt_hit_b:
                return edge
    return None


@router.get("/tensions")
def list_tensions(
    status: str | None = None, kind: str | None = None,
    user_id: str = Depends(require_user),
) -> dict:
    """张力簿列表（最新在前）；status 过滤 open/resolved/dissolved，kind 过滤 confirmed/candidate。"""
    if status and status not in personal.TENSION_STATUSES:
        raise HTTPException(422, f"status 只支持 {list(personal.TENSION_STATUSES)}")
    if kind and kind not in personal.TENSION_KINDS:
        raise HTTPException(422, f"kind 只支持 {list(personal.TENSION_KINDS)}")
    conn = _db()
    try:
        sql = "SELECT * FROM tensions WHERE user_id=?"
        params: list = [user_id]
        if status:
            sql += " AND status=?"
            params.append(status)
        if kind:
            sql += " AND kind=?"
            params.append(kind)
        sql += " ORDER BY rowid DESC"
        rows = conn.execute(sql, params).fetchall()
        results = [_tension_row(r) for r in rows]
        # 分离展示：候选与既成各自成组（界面不用自己判 kind）
        return {
            "results": results,
            "confirmed": [t for t in results if t["kind"] == "confirmed"],
            "candidates": [t for t in results if t["kind"] == "candidate"],
        }
    finally:
        conn.close()


class TensionStatusIn(BaseModel):
    status: str = Field(min_length=1)


@router.post("/tensions/{tension_id}/status")
def set_tension_status(
    tension_id: str, body: TensionStatusIn, user_id: str = Depends(require_user)
) -> dict:
    """张力状态流转（open/resolved/dissolved），留痕可追溯。"""
    conn = _db()
    try:
        try:
            out = personal.update_tension_status(conn, user_id, tension_id, body.status)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if out is None:
            raise HTTPException(404, "张力不存在或不属于该用户")
        personal.audit(conn, user_id, "tension.status", tension_id, "allowed",
                       detail=f"→{body.status}")
        out["events"] = personal.tension_events(conn, user_id, tension_id)
        return out
    finally:
        conn.close()


@router.post("/tensions/{tension_id}/confirm")
def confirm_tension(tension_id: str, user_id: str = Depends(require_user)) -> dict:
    """候选升级为既成张力（candidate → confirmed），留痕。"""
    conn = _db()
    try:
        out = personal.confirm_tension(conn, user_id, tension_id)
        if out is None:
            raise HTTPException(404, "张力不存在或不属于该用户")
        personal.audit(conn, user_id, "tension.confirm", tension_id, "allowed")
        out["events"] = personal.tension_events(conn, user_id, tension_id)
        return out
    finally:
        conn.close()


@router.post("/tensions/{tension_id}/ignore")
def ignore_tension(tension_id: str, user_id: str = Depends(require_user)) -> dict:
    """忽略候选（→ dissolved），留痕；既成张力亦可被用户判定为不成立。"""
    conn = _db()
    try:
        out = personal.update_tension_status(conn, user_id, tension_id, "dissolved")
        if out is None:
            raise HTTPException(404, "张力不存在或不属于该用户")
        personal.audit(conn, user_id, "tension.ignore", tension_id, "allowed")
        out["events"] = personal.tension_events(conn, user_id, tension_id)
        return out
    finally:
        conn.close()
