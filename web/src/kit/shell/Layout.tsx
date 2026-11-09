// 识律家族共享壳 · 布局（spec web-shell-kit「布局壳不假定宿主路由」）
//
// 这一条是踩过事故的：PackMarketView 曾在壹座语境里调用 useNavigate()，
// 谦面薄壳不挂 Router，整个页面白屏。所以本壳：
//   · MUST NOT import 任何路由库；
//   · 链接由宿主以 `renderLink` 注入；不注入时渲染纯文本（不报错、不退化出错动作）；
//   · 需要"跳转"的入口由宿主传回调；不传则不渲染该入口。
import type { ReactNode } from 'react'

export interface NavItem {
  key: string
  label: string
  /** 目标；无 href 且无 onClick 时该项不渲染为可点 */
  href?: string
  onClick?: () => void
  /** 仅当 true 时以强调态渲染 */
  active?: boolean
}

export interface ShellOptions {
  brand: ReactNode
  nav?: NavItem[]
  footer?: ReactNode
  /** 宿主注入的链接渲染器（有 Router 时用它；没有则不传） */
  renderLink?: (item: NavItem, content: ReactNode) => ReactNode
  /** 语言切换等右侧动作 */
  actions?: ReactNode
}

/** 单项渲染：注入优先 → 有 href 用 <a> → 有 onClick 用 <button> → 否则纯文本。 */
export function renderNavItem(
  item: NavItem,
  renderLink?: ShellOptions['renderLink'],
): ReactNode {
  const content = item.label
  if (renderLink) return renderLink(item, content)
  if (item.href) return <a href={item.href}>{content}</a>
  if (item.onClick) return <button type="button" onClick={item.onClick}>{content}</button>
  return <span>{content}</span>
}

export interface LayoutProps extends ShellOptions {
  children: ReactNode
  /** 测试与降级用：不渲染 header/footer 之外的多余结构 */
  className?: string
}

/**
 * 页面骨架。刻意保持无状态、无副作用、无上下文依赖——
 * 它必须能在"没有任何 Provider / Router"的树里直接渲染。
 */
export function Layout({ brand, nav = [], footer, renderLink, actions, children, className }: LayoutProps) {
  return (
    <div className={className ?? 'shell'}>
      <header className="shell__header">
        <div className="shell__brand">{brand}</div>
        {nav.length > 0 && (
          <nav className="shell__nav">
            {nav.map((item) => (
              <span key={item.key} data-active={item.active ? 'true' : undefined} className="shell__nav-item">
                {renderNavItem(item, renderLink)}
              </span>
            ))}
          </nav>
        )}
        {actions && <div className="shell__actions">{actions}</div>}
      </header>
      <main className="shell__main">{children}</main>
      {footer && <footer className="shell__footer">{footer}</footer>}
    </div>
  )
}
