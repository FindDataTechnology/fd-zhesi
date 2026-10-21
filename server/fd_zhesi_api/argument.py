"""论证结构序列化（zhesi-atlas-resilience 4.1-4.4）。

真源是 JSON（design 决策 5）：立场卡新增 `argument` 子对象——
`claim`、`premises[{id, text}]`、`edges[{from, to, type: support|attack}]`。
散文式字段（reasons / strongest_objection / my_response / stability）保持不变。

Argdown 只作**导出/交换格式**：
- 导出 `[name]: claim` + `(id) premise` + `(id) -> [name]` / `(id) ->< [name]`
- 散文字段与原始 argument 以 `// fd-zhesi-meta: {json}` 注释随文件携带，
  导入时还原——因此「导出后再导入」不丢立场、理由、最强反驳、回应、现状
- 无法映射的语法进 `warnings`（尽力解析，不静默丢弃、不猜测语义）

可机器比对（4.4）：`premise_overlap` 按前提标识与归一化文本判断两张卡是否共享前提。
"""

from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

CLAIM_NODE = "claim"
EDGE_TYPES = ("support", "attack")

# 前提标识只允许简单标识符：Argdown 的 (id) 语法与往返一致性都要求如此
_PREMISE_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,31}$")
_META_PREFIX = "// fd-zhesi-meta:"
_ARG_RE = re.compile(r"^\[([^\]]+)\]:\s*(.*)$")
_PREMISE_RE = re.compile(r"^\(([A-Za-z][A-Za-z0-9_-]{0,31})\)\s*(.*)$")
_EDGE_RE = re.compile(
    r"^\(([A-Za-z][A-Za-z0-9_-]{0,31})\)\s*(-?><|->)\s*\[([^\]]+)\]$"
)


class Premise(BaseModel):
    id: str = Field(min_length=1)
    text: str = Field(min_length=1)

    @field_validator("id")
    @classmethod
    def _id_shape(cls, v: str) -> str:
        if not _PREMISE_ID_RE.match(v):
            raise ValueError(
                f"前提标识 {v!r} 非法：只允许字母开头的字母/数字/下划线/连字符（≤32）"
            )
        return v


class Edge(BaseModel):
    from_: str = Field(alias="from", min_length=1)
    to: str = Field(min_length=1)
    type: Literal["support", "attack"]

    model_config = {"populate_by_name": True}


class Argument(BaseModel):
    """一张立场卡的论证结构。空论证（旧卡）合法：claim 可空、前提与边为空。"""

    claim: str | None = None
    premises: list[Premise] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)

    @model_validator(mode="after")
    def _consistent(self) -> "Argument":
        ids = [p.id for p in self.premises]
        if len(ids) != len(set(ids)):
            dup = sorted({i for i in ids if ids.count(i) > 1})
            raise ValueError(f"前提标识重复：{dup}")
        known = set(ids) | {CLAIM_NODE}
        for edge in self.edges:
            if edge.from_ not in known:
                raise ValueError(f"边起点 {edge.from_!r} 不是前提标识或 claim")
            if edge.to not in known:
                raise ValueError(f"边终点 {edge.to!r} 不是前提标识或 claim")
            if edge.from_ == edge.to:
                raise ValueError(f"边不能自指：{edge.from_}")
        return self


def empty_argument(position: str = "") -> dict:
    return {"claim": position or None, "premises": [], "edges": []}


def validate_argument(data: dict | None, position: str = "") -> dict:
    """校验并归一化论证结构；非法即抛 ValueError（schema 校验，4.1）。"""
    if data is None:
        return empty_argument(position)
    if not isinstance(data, dict):
        raise ValueError("argument 必须是对象")
    payload = {
        "claim": data.get("claim") or position or None,
        "premises": data.get("premises") or [],
        "edges": data.get("edges") or [],
    }
    model = Argument.model_validate(payload)
    return {
        "claim": model.claim,
        "premises": [{"id": p.id, "text": p.text} for p in model.premises],
        "edges": [
            {"from": e.from_, "to": e.to, "type": e.type} for e in model.edges
        ],
    }


# ---------------------------------------------------------------- 导出（4.2）

def export_argdown(card: dict) -> str:
    """立场卡 → Argdown 兼容文本（含主张、前提与支持/攻击关系）。

    散文字段以 meta 注释随行，供导入时还原（见模块 docstring）。
    """
    argument = card.get("argument") or empty_argument(card.get("position") or "")
    name = f"stance-{card.get('id') or 'card'}"
    claim = argument.get("claim") or card.get("position") or ""
    lines = [f"[{name}]: {claim}", ""]

    for premise in argument.get("premises") or []:
        lines.append(f"({premise['id']}) {premise['text']}")
    if argument.get("premises"):
        lines.append("")

    arrow = {"support": "->", "attack": "-><"}
    for edge in argument.get("edges") or []:
        src = edge["from"]
        dst = edge["to"]
        target = f"[{name}]" if dst == CLAIM_NODE else f"[{dst}]"
        lines.append(f"({src}) {arrow.get(edge['type'], '->')} {target}")
    if argument.get("edges"):
        lines.append("")

    meta = {
        "id": card.get("id"),
        "question": card.get("question"),
        "question_ref": card.get("question_ref"),
        "position": card.get("position"),
        "reasons": card.get("reasons"),
        "strongest_objection": card.get("strongest_objection"),
        "my_response": card.get("my_response"),
        "stability": card.get("stability"),
        "argument": argument,
    }
    lines.append(f"{_META_PREFIX} {json.dumps(meta, ensure_ascii=False)}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- 导入（4.3）

def import_argdown(text: str, position: str = "") -> tuple[dict, list[str]]:
    """Argdown 文本 → (卡片字段, warnings)。

    只做尽力解析：认识的语法还原为结构化数据，不认识的进 warnings
    （不静默丢弃、不猜测语义）。往返后立场/理由/最强反驳/回应/现状由 meta 还原。
    """
    warnings: list[str] = []
    meta: dict | None = None
    claim: str | None = None
    premises: list[dict] = []
    edges: list[dict] = []

    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(_META_PREFIX):
            payload = line[len(_META_PREFIX):].strip()
            try:
                parsed = json.loads(payload)
            except json.JSONDecodeError as exc:
                warnings.append(f"meta 注释不是合法 JSON（{exc.msg}）")
                continue
            if isinstance(parsed, dict):
                meta = parsed
            else:
                warnings.append("meta 注释不是对象")
            continue
        if line.startswith("//") or line.startswith("#"):
            continue  # 普通注释：Argdown 允许，不影响语义
        edge_m = _EDGE_RE.match(line)
        if edge_m:
            src, arrow, target = edge_m.groups()
            edges.append({
                "from": src,
                "to": CLAIM_NODE if target.startswith("stance-") else target,
                "type": "attack" if arrow == "-><" else "support",
            })
            continue
        premise_m = _PREMISE_RE.match(line)
        if premise_m:
            pid, ptext = premise_m.groups()
            if not ptext.strip():
                warnings.append(f"前提 ({pid}) 无文本，已跳过")
                continue
            premises.append({"id": pid, "text": ptext.strip()})
            continue
        arg_m = _ARG_RE.match(line)
        if arg_m:
            claim = arg_m.group(2).strip() or claim
            continue
        warnings.append(f"未识别的语法，已跳过：{line[:80]}")

    card_fields: dict = {
        "question": None,
        "question_ref": None,
        "position": position or None,
        "reasons": None,
        "strongest_objection": None,
        "my_response": None,
        "stability": None,
    }
    if meta:
        for key in card_fields:
            if meta.get(key) is not None:
                card_fields[key] = meta[key]
        if not card_fields["position"]:
            card_fields["position"] = meta.get("position")
    argument_raw = (meta or {}).get("argument") or {
        "claim": claim,
        "premises": premises,
        "edges": edges,
    }
    try:
        argument = validate_argument(argument_raw, card_fields["position"] or "")
    except ValueError as exc:
        warnings.append(f"meta 里的 argument 非法，改用正文解析结果：{exc}")
        try:
            argument = validate_argument(
                {"claim": claim, "premises": premises, "edges": edges},
                card_fields["position"] or "",
            )
        except ValueError as exc2:
            warnings.append(f"正文解析的论证结构也非法，按空论证处理：{exc2}")
            argument = empty_argument(card_fields["position"] or "")
    return {"fields": card_fields, "argument": argument}, warnings


# ------------------------------------------------------------ 机器比对（4.4）

def _norm_text(text: str) -> str:
    return " ".join((text or "").casefold().split()).strip("。．.；;，, ")


def premise_overlap(card_a: dict, card_b: dict) -> dict:
    """两张卡的前提重叠（按标识与归一化文本双重比对）。

    返回：
    - `by_id`   两张卡都出现的前提标识（原样，仅供诊断）
    - `by_text` 归一化文本一致的前提（取 a 卡标识）
    - `shared`  **实质共享**的显示标签：文本一致的才算——标识只是卡片内的局部
      编号（人人都从 P1 开始），光同号不构成共享前提，否则两张无关的卡也会被
      判成共享（宁缺毋滥）
    """
    def _premises(card: dict) -> list[dict]:
        argument = card.get("argument") or {}
        return argument.get("premises") or []

    a_prem = _premises(card_a)
    b_prem = _premises(card_b)
    a_ids = {p["id"]: p for p in a_prem}
    b_ids = {p["id"]: p for p in b_prem}
    by_id = sorted(set(a_ids) & set(b_ids))

    a_text = {_norm_text(p.get("text", "")): p["id"] for p in a_prem}
    b_text = {_norm_text(p.get("text", "")): p["id"] for p in b_prem}
    shared_text = sorted(t for t in set(a_text) & set(b_text) if t)
    by_text = [a_text[t] for t in shared_text]

    substantive: list[str] = []
    for pid in by_id:
        norm_a = _norm_text(a_ids[pid].get("text", ""))
        norm_b = _norm_text(b_ids[pid].get("text", ""))
        if norm_a and norm_a == norm_b:
            substantive.append(pid)
    for pid in by_text:
        if pid not in substantive:
            substantive.append(pid)

    labels = [f"{pid}: {a_ids[pid].get('text', '')}" for pid in substantive]
    return {
        "shared": labels,
        "by_id": by_id,
        "by_text": by_text,
        "substantive": substantive,
    }


def conclusions_opposed(card_a: dict, card_b: dict) -> bool:
    """同一问题上的不同表态即结论相反（与 axis_map 同一坐标口径）。"""
    from .axis_map import resolve

    ra = resolve(card_a.get("question", ""), card_a.get("position", ""),
                 card_a.get("question_ref"))
    rb = resolve(card_b.get("question", ""), card_b.get("position", ""),
                 card_b.get("question_ref"))
    if not ra or not rb:
        return False
    return ra.question_key == rb.question_key and ra.position != rb.position
