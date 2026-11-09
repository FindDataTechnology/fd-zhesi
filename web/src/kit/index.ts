// 识律家族共享壳（spec web-shell-kit）。导出面刻意最小：
// 只有四个子模块的公开符号，宿主 MUST NOT deep-import 内部文件。
//
// 本文件同时是"无 router 依赖"的守门点：它 MUST NOT 出现任何路由库导入。

export { createAuth, AuthError } from './auth/index'
export type { Auth, AuthConfig, AuthOptions, AuthSession } from './auth/index'

export { createI18n, assertLocaleParity, localeDiff } from './i18n/index'
export type { I18n, Locale, I18nOptions } from './i18n/index'

export { createTransport, TransportError, redact } from './transport/index'
export type { Transport, TransportOptions } from './transport/index'

export { Layout, renderNavItem } from './shell/Layout'
export type { LayoutProps, NavItem, ShellOptions } from './shell/Layout'
