"""手工种子层：Atlas 缺失时用于锚定思想邻居（zhesi-atlas-resilience 2.1）。

**这不是模型生成的坐标**：本文件的六轴取值与批判边全部取自 Philosophy Atlas
真实数据（MBGuedes，CC BY 4.0）的 24 人高影响力子集，提取自
`fd-zhesi-reference/seed/reference.db`（corpus v8.0 / whitepaper v2.1）。
抽取规则：轴完整（六轴非 NULL）且 influence_score 最高者；批判边取该子集内部的
`polarity='critical'` 关系。

为什么要有它：Atlas 站点实测不可达（2026-10-21），若没有种子层，谱闭环在
Atlas 缺失时完全无法给邻居。种子只做**降级锚定**，置信度显著下调
（`axis_map.CONFIDENCE_PENALTY["atlas"]`），并在输出里如实标注缺失层；
Atlas 恢复后重新摄取即用全量 376 人重合成（2.3）。

署名随结果下发（provenance source = `philosophy-atlas-seed`）。
"""

from __future__ import annotations

from dataclasses import dataclass

SEED_VERSION = "atlas-subset-24@corpus-v8.0"
SEED_ATTRIBUTION_SOURCE = "philosophy-atlas-seed"


@dataclass(frozen=True)
class SeedPhilosopher:
    atlas_id: int
    name_en: str
    name_zh: str
    individualism: float
    materialism: float
    rationalism: float
    determinism: float
    transcendence: float
    universalism: float

    def axes(self) -> dict[str, float]:
        return {
            "individualism": self.individualism,
            "materialism": self.materialism,
            "rationalism": self.rationalism,
            "determinism": self.determinism,
            "transcendence": self.transcendence,
            "universalism": self.universalism,
        }


# atlas_id, name_en, name_zh, ind, mat, rat, det, tra, uni
SEED_PHILOSOPHERS: tuple[SeedPhilosopher, ...] = (
    SeedPhilosopher(6, "Socrates", "苏格拉底", 6, 1, 9, 4, 7, 9),
    SeedPhilosopher(7, "Plato", "柏拉图", 3, 0, 10, 6, 10, 10),
    SeedPhilosopher(8, "Aristotle", "亞里士多德", 4, 6, 8, 7, 5, 8),
    SeedPhilosopher(13, "Augustine of Hippo", "奥古斯丁", 6, 0, 5, 8, 10, 8),
    SeedPhilosopher(15, "Thomas Aquinas", "托马斯·阿奎那", 4, 4, 9, 6, 9, 10),
    SeedPhilosopher(20, "Niccolò Machiavelli", "尼可罗·马基亚维利", 7, 8, 8, 6, 1, 6),
    SeedPhilosopher(22, "René Descartes", "勒内·笛卡儿", 7, 2, 10, 7, 8, 10),
    SeedPhilosopher(23, "Benedictus de Spinoza", "巴魯赫·斯賓諾莎", 5, 7, 10, 10, 4, 10),
    SeedPhilosopher(26, "Thomas Hobbes", "托马斯·霍布斯", 4, 9, 7, 8, 1, 6),
    SeedPhilosopher(27, "John Locke", "约翰·洛克", 8, 6, 6, 4, 5, 8),
    SeedPhilosopher(29, "David Hume", "大卫·休谟", 7, 7, 4, 6, 1, 5),
    SeedPhilosopher(30, "Jean-Jacques Rousseau", "让-雅克·卢梭", 7, 5, 5, 4, 5, 7),
    SeedPhilosopher(33, "Immanuel Kant", "伊曼努爾·康德", 7, 3, 10, 6, 7, 10),
    SeedPhilosopher(41, "Georg Wilhelm Friedrich Hegel", "黑格爾", 4, 3, 10, 9, 7, 10),
    SeedPhilosopher(43, "Karl Marx", "卡爾·馬克思", 3, 10, 7, 9, 0, 8),
    SeedPhilosopher(45, "John Stuart Mill", "约翰·斯图尔特·密尔", 8, 6, 7, 4, 2, 8),
    SeedPhilosopher(48, "Friedrich Nietzsche", "尼采", 9, 7, 4, 3, 2, 2),
    SeedPhilosopher(56, "Edmund Husserl", "埃德蒙德·胡塞爾", 6, 2, 9, 5, 5, 8),
    SeedPhilosopher(57, "Martin Heidegger", "马丁·海德格尔", 7, 3, 5, 5, 7, 4),
    SeedPhilosopher(58, "Ludwig Wittgenstein", "维特根斯坦", 7, 5, 7, 5, 2, 5),
    SeedPhilosopher(61, "Jean-Paul Sartre", "让-保罗·萨特", 10, 8, 6, 1, 2, 4),
    SeedPhilosopher(67, "Michel Foucault", "米歇尔·福柯", 8, 6, 3, 4, 2, 2),
    SeedPhilosopher(79, "Gautama Buddha", "释迦牟尼", 6, 4, 6, 7, 6, 8),
    SeedPhilosopher(90, "Confucius", "孔子", 3, 5, 6, 6, 5, 8),
)

# 子集内部的批判边（source_id, target_id, weight）
SEED_CRITICAL_EDGES: tuple[tuple[int, int, float], ...] = (
    (8, 7, 0.7),
    (29, 33, 0.9),
    (33, 41, 0.8),
    (41, 43, 0.8),
    (41, 57, 0.8),
    (48, 61, 0.4),
    (48, 67, 0.6),
    (56, 57, 0.8),
    (57, 61, 0.6),
)


def seed_rows() -> list[dict]:
    """种子层行（形状对齐 philosophers 表：atlas_id/name_en/name_zh/六轴）。"""
    return [
        {
            "atlas_id": p.atlas_id,
            "name_en": p.name_en,
            "name_zh": p.name_zh,
            **p.axes(),
        }
        for p in SEED_PHILOSOPHERS
    ]


def seed_critical_edges() -> list[dict]:
    """种子层的批判边（影响图 critical 关系，供张力候选推断用）。"""
    by_id = {p.atlas_id: p for p in SEED_PHILOSOPHERS}
    return [
        {
            "source_id": src,
            "target_id": tgt,
            "weight": weight,
            "source_name": by_id[src].name_en,
            "target_name": by_id[tgt].name_en,
            "source_name_zh": by_id[src].name_zh,
            "target_name_zh": by_id[tgt].name_zh,
        }
        for src, tgt, weight in SEED_CRITICAL_EDGES
        if src in by_id and tgt in by_id
    ]
