// 识律家族共享壳 · 状态徽章原语（change lex-web-shell-convergence 5.2）
//
// ## 为什么是"降级实现"而不是与 paas 逐文件同源
//
// 原始判据要求"原语文件与上游逐文件哈希一致"。实测该判据在本仓做不到：
// paas 的 `status-pill.tsx` 依赖 `clsx` + `tailwind-merge`（`@/lib/utils` 的 `cn`）、
// `@/*` 路径别名、以及 `--color-status-*` 主题令牌；三个宿主三者全无。
// 逐文件一致 = 连带端口依赖层与主题层，既超出本 change 范围，又会改动宿主各自调色板。
//
// 本条裁决（2026-11-10）：走最小可用路径，**自建等价原语**——
// 契约（props 形状）与上游对齐，实现零外部依赖：
//   · 类名拼接自己写（`./cn`），不引 tailwind-merge；
//   · 路径用相对导入，不要 `@/*` 别名；
//   · 调色板不内置，由宿主经 `toneClassName` 注入；未注入时退化到 CSS 变量
//     （带 fallback，因此宿主零配置也能显示，只是配色朴素）。
//
// **解除条件（满足任一条即可换回真·同源）**：
//   1. paas 侧导出可独立消费的原语包（含 `cn`、别名解析、`--color-status-*` 令牌），
//      或
//   2. 三宿主统一接入该设计系统依赖层（tailwind 版本与令牌齐平）。
// 届时本文件整体替换为上游实现的再导出，`StatusPillProps` 保持不变。
import type { CSSProperties, ReactNode } from 'react'
import { cn } from './cn'

export type StatusTone = 'neutral' | 'positive' | 'warn' | 'danger' | 'info'

/** 未注入 toneClassName 时的兜底配色（CSS 变量优先，便于宿主统一主题）。 */
const FALLBACK_STYLE: Record<StatusTone, CSSProperties> = {
  neutral: { borderColor: 'var(--fd-status-neutral-border, #d4d4d4)', color: 'var(--fd-status-neutral-fg, #525252)' },
  positive: { borderColor: 'var(--fd-status-positive-border, #a7d7b5)', color: 'var(--fd-status-positive-fg, #1f6b3b)' },
  warn: { borderColor: 'var(--fd-status-warn-border, #fcd34d)', color: 'var(--fd-status-warn-fg, #92400e)' },
  danger: { borderColor: 'var(--fd-status-danger-border, #fca5a5)', color: 'var(--fd-status-danger-fg, #991b1b)' },
  info: { borderColor: 'var(--fd-status-info-border, #93c5fd)', color: 'var(--fd-status-info-fg, #1e40af)' },
}

const FALLBACK_BG: Record<StatusTone, string> = {
  neutral: 'var(--fd-status-neutral-bg, transparent)',
  positive: 'var(--fd-status-positive-bg, transparent)',
  warn: 'var(--fd-status-warn-bg, #fffbeb)',
  danger: 'var(--fd-status-danger-bg, #fef2f2)',
  info: 'var(--fd-status-info-bg, #eff6ff)',
}

export interface StatusPillProps {
  /** 文案由宿主给（本层不接 i18n——壳的文案经 props，见 5.1 纪律二） */
  children: ReactNode
  tone?: StatusTone
  /** 宿主整串类名；给了就不再用 CSS 变量兜底 */
  toneClassName?: Partial<Record<StatusTone, string>>
  /** 深色场地（hero/页脚）由宿主决定配色，本层只透出 data-variant */
  variant?: 'light' | 'dark'
  /**
   * 宿主的**尺寸/间距/字重/颜色**类名（如 `shrink-0 px-2 py-0.5 text-xs`）。
   *
   * 原语故意不内置这些：三宿主当前的 pill 分别是 `px-2.5 … font-medium` 与
   * `px-2 …`（无 font-medium），内置任何一套都会让另一套的视觉变掉。
   * 抽取公共组件的第一要求是**替换后像素一致**，所以排版归宿主、形状归原语。
   */
  className?: string
  title?: string
  /** 前置图形（圆点/双点/SVG），宿主自带 */
  icon?: ReactNode
}

/**
 * 状态徽章：圆角 pill 的**形状 + 语义**（tone/variant/a11y），不含排版与调色板。
 *
 * 分工：原语给 `rounded-full border` 与 `data-tone`/`data-variant`；
 * 宿主的类名走 `className`（尺寸/间距/字重），配色走 `toneClassName`
 * 或 CSS 变量 `--fd-status-*`。
 */
export function StatusPill({
  children,
  tone = 'neutral',
  toneClassName,
  variant = 'light',
  className,
  title,
  icon,
}: StatusPillProps) {
  const injected = toneClassName?.[tone]
  const style: CSSProperties | undefined = injected
    ? undefined
    : { ...FALLBACK_STYLE[tone], background: FALLBACK_BG[tone] }

  return (
    <span
      title={title}
      data-tone={tone}
      data-variant={variant}
      style={style}
      className={cn('inline-flex items-center rounded-full border', injected, className)}
    >
      {icon}
      {children}
    </span>
  )
}
