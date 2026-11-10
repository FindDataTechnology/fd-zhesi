// 主题切换机制（change lex-web-shell-convergence 5.4）
//
// 只做一件事：把 `data-theme` 写到根元素上，让 `primitives/tokens.css` 的暗色组生效。
//
// 为什么不放到 `i18n/` 或 `shell/`：主题是**原语层**的附属能力（令牌与变量都在这一层），
// 与文案、路由无关。宿主不接主题就完全不用 import 它。
//
// 为什么不读 `prefers-color-scheme`：见 tokens.css 顶部——跟随系统是宿主的决定，
// 本层只提供机制。宿主若要跟随系统，自己 `matchMedia('(prefers-color-scheme: dark)')`
// 后调用本函数即可。

export type ThemeName = 'light' | 'dark'

const THEME_ATTR = 'data-theme'

/** 元素类型收窄成"能设属性"的最小面，便于单测传入假对象（不必起 DOM）。 */
export interface ThemeRoot {
  setAttribute(name: string, value: string): void
  getAttribute(name: string): string | null
  removeAttribute?(name: string): void
}

/**
 * 设定主题。返回设定前的值（便于回滚/测试断言）。
 *
 * 幂等：重复设置同一主题不会产生额外副作用。
 */
export function applyTheme(root: ThemeRoot, theme: ThemeName): ThemeName | null {
  const previous = readTheme(root)
  root.setAttribute(THEME_ATTR, theme)
  return previous
}

/** 读取当前主题；未设置时返回 `null`（不等于 light——调用方要知道"宿主没表态"）。 */
export function readTheme(root: ThemeRoot): ThemeName | null {
  const value = root.getAttribute(THEME_ATTR)
  return value === 'dark' || value === 'light' ? value : null
}

/** 清掉显式主题，回到宿主/CSS 的默认（亮）。 */
export function clearTheme(root: ThemeRoot): void {
  if (typeof root.removeAttribute === 'function') root.removeAttribute(THEME_ATTR)
  // 没有 removeAttribute 的实现（如极简假对象）退化为写成 light：语义等价于"回到默认"
  else root.setAttribute(THEME_ATTR, 'light')
}
