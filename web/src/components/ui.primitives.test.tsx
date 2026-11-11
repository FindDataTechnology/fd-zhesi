// 状态控件已改用共享壳原语（change lex-web-shell-convergence 5.3）
//
// 同一份哨兵在本宿主（fd-zhesi）的版本：本宿主只有 `StabilityBadge` 一种徽标，
// **没有**引证/需补证/核验三标（见 5.1 映射表）——因此这里显式断言它们不存在，
// 防止有人从兄弟宿主"顺手照抄"回来。
//
// 守三件事：
//   1. 替换是真的（从 `kit/primitives` 导入、不再自拼 pill 外壳）；
//   2. 视觉不漂移（尺寸/间距/字重/配色类名仍是宿主原值）；
//   3. a11y 只增不减（错误态 role=alert、加载态 role=status）。
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'

import { EmptyLine, ErrorBox, Loading, StabilityBadge } from './ui'

const UI_SRC = readFileSync(join(__dirname, 'ui.tsx'), 'utf8')
const stripComments = (s: string) =>
  s.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '')
const UI_CODE = stripComments(UI_SRC)

describe('ui.tsx 已换用原语', () => {
  it('从 kit/primitives 导入状态类原语', () => {
    expect(UI_CODE).toMatch(/from\s+['"]\.\.\/kit\/primitives\/index['"]/)
    for (const name of ['LoadingState', 'ErrorState', 'EmptyState', 'StatusPill']) {
      expect(UI_CODE, `未导入 ${name}`).toContain(name)
    }
  })

  it('不再自己拼 pill 外壳（避免两套实现并存）', () => {
    const rawPills = [...UI_CODE.matchAll(/<span[^>]*className=\{?[`'"][^>]*rounded-full/g)]
    expect(rawPills.length, '仍有自造 pill 外壳').toBe(0)
  })

  it('DegradeBox 保持宿主自有（诚实降级契约不并入通用错误态）', () => {
    expect(UI_CODE).toMatch(/export function DegradeBox/)
    expect(UI_CODE).not.toMatch(/DegradeBox[\s\S]{0,200}ErrorState/)
  })

  it('本宿主不持有兄弟宿主的三个引证/核验徽标', () => {
    for (const name of ['CitationBadge', 'WarnBadge', 'VerifyStatusBadge']) {
      expect(UI_CODE, `${name} 不该出现在 fd-zhesi`).not.toContain(`export function ${name}`)
    }
  })
})

describe('视觉类名仍是宿主原值', () => {
  it('加载态与空态沿用 text-neutral-400 系，不是原语的 opacity 兜底', () => {
    expect(renderToStaticMarkup(<Loading />)).toContain('text-neutral-400')
    expect(renderToStaticMarkup(<EmptyLine>空</EmptyLine>)).toContain('text-neutral-400')
  })

  it('错误盒沿用 red-50/red-800 调色板', () => {
    const html = renderToStaticMarkup(<ErrorBox message="boom" />)
    expect(html).toContain('bg-red-50')
    expect(html).toContain('text-red-800')
    expect(html).not.toContain('--fd-error-bg')
  })

  it('稳定性徽标的配色走令牌变量（5.4b 起），尺寸类名保持原值', () => {
    // 5.4b 之前这里断言的是 `bg-green-50` 这类 Tailwind 类名；改为变量路径后**类名本来就不该出现**——
    // 配色交给 --fd-status-* ，由主题切换生效。所以哨兵断言的"契约"变了：
    // ① 尺寸/间距类名仍在（视觉不漂移）；② 配色出现在 var() 里（而不是写死类名）。
    const stable = renderToStaticMarkup(<StabilityBadge s="stable" />)
    expect(stable).toContain('px-2')
    expect(stable).toContain('py-0.5')
    expect(stable).toContain('text-xs')
    expect(stable).toContain('var(--fd-status-positive-')
    expect(stable).not.toMatch(/bg-green-50|text-green-800/)

    const wavering = renderToStaticMarkup(<StabilityBadge s="wavering" />)
    expect(wavering).toContain('var(--fd-status-warn-')

    const shelved = renderToStaticMarkup(<StabilityBadge s="shelved" />)
    expect(shelved).toContain('var(--fd-status-neutral-')
  })

  it('未知稳定性退回 neutral 令牌（不 panic、不空白）', () => {
    // @ts-expect-error 故意传非法值
    const html = renderToStaticMarkup(<StabilityBadge s="weird" />)
    expect(html).toContain('data-tone="neutral"')
    expect(html).toContain('var(--fd-status-neutral-')
  })
})

describe('a11y 只增不减', () => {
  it('加载态 role=status，错误态 role=alert', () => {
    expect(renderToStaticMarkup(<Loading />)).toContain('role="status"')
    expect(renderToStaticMarkup(<ErrorBox message="x" />)).toContain('role="alert"')
  })

  it('401 时仍给出令牌提示', () => {
    expect(renderToStaticMarkup(<ErrorBox message="denied" code={401} />)).toContain('mt-1 text-xs')
  })
})
