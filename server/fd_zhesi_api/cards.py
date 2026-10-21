"""个人层立场卡 API（task 3.2；zhesi-atlas-resilience 4.1-4.4 论证结构）。

全路由要求用户授权（task 3.3）；数据只落个人层自有库（物理分库铁律）。

论证结构（4.1-4.4）：
- `POST /{card_id}/argument`  写入结构化论证（claim/premises/support|attack），schema 校验
- `GET  /{card_id}/argdown`   Argdown 导出（含散文式字段的 meta 注释）
- `POST /argdown`             Argdown 导入 → 新卡（未识别语法进 warnings）
- `GET  /compare`             两卡前提重叠与结论冲突（可机器比对）
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from . import argument as argmod
from . import personal
from .auth import require_user

router = APIRouter(prefix="/api/v1/cards", tags=["stance-cards"])


class CardCreate(BaseModel):
    question: str = Field(min_length=1)
    position: str = Field(min_length=1)
    reasons: str | None = None
    question_ref: str | None = None  # 参照系坐标，如 "survey-2020:free will"


class ObjectionIn(BaseModel):
    objection: str = Field(min_length=1)


class ResponseIn(BaseModel):
    my_response: str = Field(min_length=1)
    stability: str | None = Field(default=None)


class ChangeIn(BaseModel):
    position: str = Field(min_length=1)
    reasons: str | None = None


class ArgumentIn(BaseModel):
    claim: str | None = None
    premises: list[dict] = Field(default_factory=list)
    edges: list[dict] = Field(default_factory=list)


class ArgdownIn(BaseModel):
    text: str = Field(min_length=1)
    question: str | None = None
    position: str | None = None
    question_ref: str | None = None


def _db():
    conn = personal.connect()
    personal.migrate(conn)
    return conn


@router.post("", status_code=201)
def create_card(body: CardCreate, user_id: str = Depends(require_user)) -> dict:
    conn = _db()
    try:
        card = personal.create_card(
            conn, user_id, body.question, body.position, body.reasons, body.question_ref
        )
        personal.audit(conn, user_id, "card.create", card["id"], "allowed")
        return card
    finally:
        conn.close()


@router.get("")
def list_cards(status: str = "active", user_id: str = Depends(require_user)) -> dict:
    if status not in ("active", "sealed"):
        raise HTTPException(422, "status 只支持 active/sealed")
    conn = _db()
    try:
        return {"results": personal.list_cards(conn, user_id, status)}
    finally:
        conn.close()


@router.get("/annals")
def annals(user_id: str = Depends(require_user)) -> dict:
    conn = _db()
    try:
        return {"results": personal.list_annals(conn, user_id)}
    finally:
        conn.close()


@router.get("/compare")
def compare(
    a: str = Query(min_length=1), b: str = Query(min_length=1),
    user_id: str = Depends(require_user),
) -> dict:
    """两卡可机器比对（4.4）：共享前提 + 结论是否相反。"""
    conn = _db()
    try:
        card_a = personal.get_card(conn, user_id, a)
        card_b = personal.get_card(conn, user_id, b)
        if not card_a or not card_b:
            raise HTTPException(404, "卡不存在或不属于该用户")
        overlap = argmod.premise_overlap(card_a, card_b)
        return {
            "a": a,
            "b": b,
            "shared_premises": overlap["shared"],
            "shared_by_id": overlap["by_id"],
            "shared_by_text": overlap["by_text"],
            "conclusions_opposed": argmod.conclusions_opposed(card_a, card_b),
            "shares_premises": bool(overlap["shared"]),
        }
    finally:
        conn.close()


@router.post("/argdown", status_code=201)
def import_argdown_card(body: ArgdownIn, user_id: str = Depends(require_user)) -> dict:
    """Argdown 导入 → 新卡（4.3）。往返后立场/理由/最强反驳/回应/现状均保留。"""
    parsed, warnings = argmod.import_argdown(body.text)
    fields = parsed["fields"]
    question = body.question or fields["question"]
    position = fields["position"] or body.position
    if not question or not position:
        raise HTTPException(
            422,
            "Argdown 缺少问题或立场：请在 meta 注释里提供（导出文件自带），"
            "或用 question/position 参数补齐（不猜测立场）",
        )
    conn = _db()
    try:
        card = personal.create_card(
            conn, user_id, question, position, fields["reasons"],
            body.question_ref or fields["question_ref"],
        )
        if fields["strongest_objection"]:
            card = personal.record_objection(
                conn, user_id, card["id"], fields["strongest_objection"]
            ) or card
        if fields["my_response"]:
            card = personal.record_response(
                conn, user_id, card["id"], fields["my_response"], fields["stability"]
            ) or card
        card = personal.set_argument(conn, user_id, card["id"], parsed["argument"]) or card
        personal.audit(conn, user_id, "card.import_argdown", card["id"], "allowed",
                       detail=f"warnings={len(warnings)}")
        return {"card": card, "warnings": warnings}
    finally:
        conn.close()


@router.get("/{card_id}")
def get_card(card_id: str, user_id: str = Depends(require_user)) -> dict:
    conn = _db()
    try:
        card = personal.get_card(conn, user_id, card_id)
        if not card:
            raise HTTPException(404, "卡不存在或不属于该用户")
        return card
    finally:
        conn.close()


@router.post("/{card_id}/argument")
def set_argument(
    card_id: str, body: ArgumentIn, user_id: str = Depends(require_user)
) -> dict:
    """写入结构化论证（4.1）：claim / premises / support|attack 边，schema 校验。"""
    conn = _db()
    try:
        card = personal.get_card(conn, user_id, card_id)
        if not card:
            raise HTTPException(404, "卡不存在或不属于该用户")
        try:
            normalized = argmod.validate_argument(body.model_dump(), card["position"])
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        updated = personal.set_argument(conn, user_id, card_id, normalized)
        if not updated:
            raise HTTPException(404, "卡不存在或已封存")
        personal.audit(conn, user_id, "card.argument", card_id, "allowed",
                       detail=f"premises={len(normalized['premises'])},"
                              f" edges={len(normalized['edges'])}")
        return updated
    finally:
        conn.close()


@router.get("/{card_id}/argdown")
def export_argdown(card_id: str, user_id: str = Depends(require_user)) -> dict:
    """Argdown 导出（4.2）：含主张、前提与支持/攻击关系。"""
    conn = _db()
    try:
        card = personal.get_card(conn, user_id, card_id)
        if not card:
            raise HTTPException(404, "卡不存在或不属于该用户")
        return {"card_id": card_id, "format": "argdown",
                "text": argmod.export_argdown(card)}
    finally:
        conn.close()


@router.post("/{card_id}/objection")
def objection(card_id: str, body: ObjectionIn, user_id: str = Depends(require_user)) -> dict:
    """最强反驳入卡（4.2 辩闭环调用面；呈现与来源引用由 4.2 生成）。"""
    conn = _db()
    try:
        card = personal.record_objection(conn, user_id, card_id, body.objection)
        if not card:
            raise HTTPException(404, "卡不存在或已封存")
        return card
    finally:
        conn.close()


@router.post("/{card_id}/response")
def response(card_id: str, body: ResponseIn, user_id: str = Depends(require_user)) -> dict:
    conn = _db()
    try:
        card = personal.record_response(
            conn, user_id, card_id, body.my_response, body.stability
        )
        if not card:
            raise HTTPException(404, "卡不存在或已封存")
        return card
    finally:
        conn.close()


@router.post("/{card_id}/change")
def change(card_id: str, body: ChangeIn, user_id: str = Depends(require_user)) -> dict:
    """立场变更：旧卡封存入年轮、新卡开卡，历史可回溯。"""
    conn = _db()
    try:
        card = personal.change_position(conn, user_id, card_id, body.position, body.reasons)
        if not card:
            raise HTTPException(404, "卡不存在或已封存")
        personal.audit(conn, user_id, "card.change", card_id, "allowed",
                       detail=f"superseded_by={card['id']}")
        return card
    finally:
        conn.close()
