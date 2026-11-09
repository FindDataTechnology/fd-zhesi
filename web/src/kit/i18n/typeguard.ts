// 类型层守卫：en 必须与 zh 同形（spec web-shell-kit 3.1）。
//
// 本文件不是测试，由 `tsc -p tsconfig.app.json` 检查。每一行都在用编译错误
// 证明"少一个键过不去"：删掉某条 `@ts-expect-error` 后若该行不再报错，
// tsc 会反过来报"未使用的 @ts-expect-error"——双向自证，不会假绿。
import type { SameShape } from './index'

type Zh = { nav: { home: string; console: string }; action: { submit: string } }
type En = SameShape<Zh>

/** 同形：通过 */
export const okEn: En = { nav: { home: 'Home', console: 'Console' }, action: { submit: 'Submit' } }

/** 少一个键：必须报错 */
// @ts-expect-error nav.console 缺失
export const missingKey: En = { nav: { home: 'Home' }, action: { submit: 'Submit' } }

/** 多一个键：必须报错（对象字面量多余属性） */
// @ts-expect-error bonus 是多余键
export const extraKey: En = { nav: { home: 'H', console: 'C' }, action: { submit: 'S' }, bonus: 'B' }
