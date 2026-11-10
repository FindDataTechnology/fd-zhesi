// 识律家族共享壳 · 加载/错误/空态原语（change lex-web-shell-convergence 5.2）
//
// 与 `status-pill` 同一套降级策略：契约与上游 `states-kit` 对齐，实现零外部依赖，
// 文案与配色全部经 props（本层不接 i18n、不内置调色板）。解除条件见 status-pill 顶部注释。
//
// 三个原语刻意分开导出，而不是给一个 `State` + `kind` 枚举：
// 宿主现有代码就是 `Loading` / `ErrorBox` / `EmptyLine` 三个名字（见 PRIMITIVE-MAP §一），
// 分开导出让宿主替换时是一行改 import，不需要把调用点改成分支。
import type { ReactNode } from 'react'
import { cn } from './cn'

export interface LoadingStateProps {
  /** 「加载中」文案，由宿主给 */
  label: ReactNode
  /**
   * 宿主的外观类名。**给了就完全替代兜底**（不是叠加）——原因见 StatusPill 的
   * `className` 注释：宿主的加载态是 `text-neutral-400`、有的是 `opacity-70`，
   * 叠加会产生"既变灰又变淡"的视觉漂移。
   */
  className?: string
}

/** 加载态：一行脉冲小字。不画骨架屏——骨架屏要按内容形状定制，属于宿主的事。 */
export function LoadingState({ label, className }: LoadingStateProps) {
  return (
    <p role="status" aria-live="polite" className={className ?? 'text-sm opacity-70'}>
      {label}
    </p>
  )
}

export interface ErrorStateProps {
  /** 主错误文案（宿主已本地化） */
  label: ReactNode
  /** 具体原因，如上游返回的 message */
  detail?: string
  /** 额外提示，如「令牌可能已过期」 */
  hint?: ReactNode
  /** 追加类名（尺寸/间距留给下面那个 toneClassName，避免覆盖冲突） */
  className?: string
  /** 配色整串（`border-red-200 bg-red-50 text-red-800`）；不给则用 CSS 变量兜底 */
  toneClassName?: string
}

/**
 * 错误态：一块可读的红框。
 *
 * `role="alert"` 是刻意加的：宿主原来的自造实现都没有它，屏幕阅读器不会播报
 * 「加载失败了」。这属于抽取时顺带修正，不改变视觉。
 *
 * 盒子的**形状与内距**（`rounded-lg border px-4 py-3 text-sm`）三宿主完全一致，
 * 所以放在原语里；只有颜色走 toneClassName / CSS 变量。
 */
export function ErrorState({ label, detail, hint, className, toneClassName }: ErrorStateProps) {
  return (
    <div
      role="alert"
      className={cn('rounded-lg border px-4 py-3 text-sm', toneClassName, className)}
      style={
        toneClassName
          ? undefined
          : {
              borderColor: 'var(--fd-error-border, #fca5a5)',
              background: 'var(--fd-error-bg, #fef2f2)',
              color: 'var(--fd-error-fg, #991b1b)',
            }
      }
    >
      <p>
        {label}
        {detail ? `：${detail}` : ''}
      </p>
      {hint ? <div className="mt-1 text-xs opacity-80">{hint}</div> : null}
    </div>
  )
}

export interface EmptyStateProps {
  children: ReactNode
  /** 给了就完全替代兜底（同 LoadingState） */
  className?: string
}

/** 空态：一行淡淡的说明。空态不是错误，所以不带 role=alert。 */
export function EmptyState({ children, className }: EmptyStateProps) {
  return <p className={className ?? 'text-sm opacity-60'}>{children}</p>
}
