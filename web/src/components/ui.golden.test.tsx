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

  it('StabilityBadge × 三态', () => {
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
    expectSameClasses(renderToStaticMarkup(<StabilityBadge s="stable" />), [
      ...base,
      'border-green-300',
      'bg-green-50',
      'text-green-800',
    ])
    expectSameClasses(renderToStaticMarkup(<StabilityBadge s="wavering" />), [
      ...base,
      'border-amber-300',
      'bg-amber-50',
      'text-amber-800',
    ])
    expectSameClasses(renderToStaticMarkup(<StabilityBadge s="shelved" />), [
      ...base,
      'border-neutral-300',
      'bg-neutral-100',
      'text-neutral-500',
    ])
  })

  it('未知稳定性沿用 shelved 兜底', () => {
    // @ts-expect-error 故意传非法值，验证运行时兜底
    const got = classesOf(renderToStaticMarkup(<StabilityBadge s="weird" />))
    expect(got.has('bg-neutral-100')).toBe(true)
    expect(got.has('text-neutral-500')).toBe(true)
  })
})
