// 识律家族共享壳（spec web-shell-kit）。导出面刻意最小：
// 只有四个子模块的公开符号，宿主 MUST NOT deep-import 内部文件。
//
// 本文件同时是"无 router 依赖"的守门点：它 MUST NOT 出现任何路由库导入。

export { createAuth, AuthError } from './auth/index'
export { ssoHintSeen, ssoHintMark, ssoHintClear } from './auth/sso-hint'
export { runSsoOnMount } from './auth/sso-mount'
export type { SsoMountOptions } from './auth/sso-mount'
export type { Auth, AuthConfig, AuthOptions, AuthSession } from './auth/index'

export { createI18n, assertLocaleParity, localeDiff } from './i18n/index'
export type { I18n, Locale, I18nOptions } from './i18n/index'

export { createTransport, TransportError, redact } from './transport/index'
export type { Transport, TransportOptions } from './transport/index'

export { useI18n } from './i18n/react'
export type { UseI18nResult } from './i18n/react'

export { Layout, renderNavItem } from './shell/Layout'
export type { LayoutProps, NavItem, ShellOptions } from './shell/Layout'

// 设计原语（group 5，2026-11-10 降级实现）：零外部依赖，文案与调色板经 props。
// 何时换回 paas 同源实现（解除条件）写在 primitives/status-pill.tsx 顶部注释。
export { StatusPill, LoadingState, ErrorState, EmptyState, cn } from './primitives/index'
export type {
  StatusPillProps,
  StatusTone,
  LoadingStateProps,
  ErrorStateProps,
  EmptyStateProps,
  ClassValue,
} from './primitives/index'
