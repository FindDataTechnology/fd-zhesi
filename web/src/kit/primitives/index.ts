// 原语层出口。宿主只从这里导入，MUST NOT deep-import 内部文件
// （与 web-kit/index.ts 的同一条纪律一致）。
export { cn } from './cn'
export type { ClassValue } from './cn'

export { StatusPill } from './status-pill'
export type { StatusPillProps, StatusTone } from './status-pill'

export { LoadingState, ErrorState, EmptyState } from './states-kit'
export type { LoadingStateProps, ErrorStateProps, EmptyStateProps } from './states-kit'

// 主题机制（5.4）。**令牌本身是 opt-in 的 CSS**：宿主需要时自行
// `import './kit/primitives/tokens.css'`——不 import 就完全不影响现有观感。
export { applyTheme, readTheme, clearTheme } from './theme'
export type { ThemeName, ThemeRoot } from './theme'
