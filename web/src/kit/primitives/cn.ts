// 识律家族共享壳 · 原语层的类名拼接（零依赖）
//
// 为什么自己写而不是装 clsx + tailwind-merge：
// 1. 三个宿主的 package.json 都没有这两个依赖，装它们等于让"抽取公共组件"这件事
//    反过来给宿主增加依赖面——宿主会因此有理由拒绝替换；
// 2. tailwind-merge 解决的是"同族类名冲突"（px-2 与 px-4 谁赢）。本层刻意不做
//    这种事：原语只接收**整串**调色板类名（由宿主给），自己不拼同族冲突类，
//    所以只需要"过滤假值 + 拼接"这一件事。
//
// 若将来宿主统一到 paas 的设计系统（含 cn/tailwind-merge），本文件可整体换成
// 上游实现——接口不变。
export type ClassValue = string | false | null | undefined | 0

export function cn(...parts: ClassValue[]): string {
  const out: string[] = []
  for (const part of parts) {
    if (!part) continue
    const text = String(part).trim()
    if (text) out.push(text)
  }
  return out.join(' ')
}
