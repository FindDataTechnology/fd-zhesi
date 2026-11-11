// 7.3 视觉等价的机器可验部分：类名 golden 比对（fd-zhesi）
//
// golden = 改前 `ui.tsx` 的类名字面量（`git show` 可复核）。集合相等即"没丢类、没多类"。
// 人眼仍需看的部分（颜色值正确性、字体渲染、flex 上下文收缩）不在这里，见 tasks.md 7.3。
import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'

import { EmptyLine, ErrorBox, Loading, StabilityBadge } from './ui'

function classesOf(html: string): Set<string> {
  const m = html.match(/class="([^"]*)"/)
  if (!m) throw new Error(`渲染结果里没有 class：${html.slice(0, 120)}`)
  return new Set(m[1].split(/\s+/).filter(Boolean))
}

function expectSameClasses(html: string, golden: string[]) {
  const got = classesOf(html)
  const want = new Set(golden)
  const missing = [...want].filter((c) => !got.has(c))
  const extra = [...got].filter((c) => !want.has(c))
  expect({ missing, extra }).toEqual({ missing: [], extra: [] })
}

describe('7.3 golden：改前后 class 集合逐控件相等（fd-zhesi）', () => {
  it('Loading', () => {
    expectSameClasses(renderToStaticMarkup(<Loading />), [
      'animate-pulse',
      'text-sm',
      'text-neutral-400',
    ])
  })

  it('EmptyLine', () => {
    expectSameClasses(renderToStaticMarkup(<EmptyLine>空</EmptyLine>), [
      'text-sm',
      'text-neutral-400',
    ])
  })

  it('ErrorBox（盒子本体）', () => {
    expectSameClasses(renderToStaticMarkup(<ErrorBox message="boom" />), [
      'rounded-lg',
      'border',
      'border-red-200',
      'bg-red-50',
      'px-4',
      'py-3',
      'text-sm',
      'text-red-800',
    ])
  })

  // 5.4b 起 StabilityBadge 走 CSS 变量配色，类名里**不再有颜色类**。
  // 因此"视觉等价"的主证据从"类名集合相等"改为**像素级 0 差异**
  // （见 fd-lex/scripts/compare_screenshots.js 的实测：三站 5 页 0/6053760 等）。
  // 这里仍守住"形状与间距类名一个不丢"，那是像素不变的机器前置条件。
  it('StabilityBadge × 三态：形状/间距类名不变（配色已改走令牌）', () => {
    const base = [
      'inline-flex',
      'items-center',
      'rounded-full',
      'border',
      'shrink-0',
      'px-2',
      'py-0.5',
      'text-xs',
    ]
    for (const [state, tone] of [
      ['stable', 'positive'],
      ['wavering', 'warn'],
      ['shelved', 'neutral'],
    ]) {
      const html = renderToStaticMarkup(<StabilityBadge s={state as never} />)
      expectSameClasses(html, base)
      // 配色必须来自令牌，且 tone 与状态对应
      expect(html).toContain(`data-tone="${tone}"`)
      expect(html).toContain(`var(--fd-status-${tone}-`)
    }
  })

  it('未知稳定性沿用 neutral 令牌兜底', () => {
    // @ts-expect-error 故意传非法值，验证运行时兜底
    const html = renderToStaticMarkup(<StabilityBadge s="weird" />)
    expectSameClasses(html, [
      'inline-flex',
      'items-center',
      'rounded-full',
      'border',
      'shrink-0',
      'px-2',
      'py-0.5',
      'text-xs',
    ])
    expect(html).toContain('data-tone="neutral"')
  })
})
