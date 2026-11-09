// 识律家族共享壳 · 双语（spec web-shell-kit「双语以类型化文案模块承载」）
//
// 键位由类型约束：宿主把自己的文案声明成 `const zh = {...} as const`，
// `createI18n({zh, en})` 的类型参数会强制 en 具有完全相同的键形状——
// 少一个键在 `tsc` 阶段就红，而不是等用户看到空白。
//
// 纪律：MUST NOT 内含任何语言字面量（本文件自身也不带文案）。

export type Locale = 'zh' | 'en'

export interface I18n<T> {
  locale(): Locale
  setLocale(next: Locale): void
  /** 取文案；路径如 'nav.home'。缺失时返回路径本身而不是空串（便于发现） */
  t(path: string): string
  messages(): T
}

/** 叶子一律放宽为 string，但**键结构必须逐一相同**。 */
export type SameShape<T> = T extends string
  ? string
  : T extends Record<string, unknown>
    ? { [K in keyof T]: SameShape<T[K]> }
    : string

function walk(obj: unknown, prefix = '', out: Record<string, string> = {}) {
  if (obj && typeof obj === 'object') {
    for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
      walk(v, prefix ? `${prefix}.${k}` : k, out)
    }
  } else {
    out[prefix] = String(obj)
  }
  return out
}

/** 两语言键位差集：missing=有 base 无 other；extra=有 other 无 base。 */
export function localeDiff(base: unknown, other: unknown): { missing: string[]; extra: string[] } {
  const a = Object.keys(walk(base)).sort()
  const b = new Set(Object.keys(walk(other)))
  const as = new Set(a)
  return {
    missing: a.filter((k) => !b.has(k)),
    extra: [...b].filter((k) => !as.has(k)).sort(),
  }
}

/** 对等门：任一方向有差即抛，并指名键。 */
export function assertLocaleParity(zh: unknown, en: unknown): void {
  const { missing, extra } = localeDiff(zh, en)
  if (missing.length || extra.length) {
    const parts: string[] = []
    if (missing.length) parts.push(`en 缺 ${missing.length} 键：${missing.slice(0, 5).join(', ')}`)
    if (extra.length) parts.push(`en 多 ${extra.length} 键：${extra.slice(0, 5).join(', ')}`)
    throw new Error(`语言键位不对等 —— ${parts.join('；')}`)
  }
}

export interface I18nOptions<T extends Record<string, unknown>> {
  /**
   * 形状由 zh 决定。
   *
   * 注意：这里 MUST 是裸的 `T`，不能写成 `SameShape<T>`——从映射/条件类型
   * 反推 T 会失败并退回约束上界，于是窄 en 也被判"可接受"，少键照样过编译
   * （2026-11-10 两次实测：先 NoInfer、后 Leaves 都拦不住）。
   */
  zh: T
  /** en 必须与 zh 同形（键结构逐一相同，叶子放宽为 string）。 */
  en: SameShape<T>
  initial?: Locale
  /** 初始语言的来源（如浏览器语言）；缺省 zh */
  detect?: () => Locale | null
}

export function createI18n<T extends Record<string, unknown>>(options: I18nOptions<T>): I18n<T> {
  const { zh, en } = options as { zh: T; en: SameShape<T> }
  // 构建期即校验：宿主包进 CI 的对等门在运行前就失败
  assertLocaleParity(zh, en)
  const tables: Record<Locale, Record<string, string>> = {
    zh: walk(zh),
    en: walk(en),
  }
  let current: Locale = options.initial ?? options.detect?.() ?? 'zh'

  return {
    locale: () => current,
    setLocale(next: Locale) {
      current = next
    },
    t(path: string): string {
      const value = tables[current][path]
      return value ?? path
    },
    messages: () => (current === 'zh' ? zh : en) as unknown as T,
  }
}
