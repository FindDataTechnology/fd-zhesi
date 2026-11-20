# fd-zhesi

哲思（zhesi）独立产品线门面单仓：web 三入口（`/` 官网 landing、`/workbench` 工作台、`/admin` 管理后台）+ FastAPI 服务端（个人层：立场卡/张力簿/思想年轮的自有存储）。

依据 `openspec/changes/zhesi-worldview-workshop`（task 6.1，骨架）。技术栈照 fd 舰队配方：React 19 + Vite + TS + Tailwind v4 + i18next 双语；服务端 Python FastAPI；部署 cheap fd-prod + TCR + ArgoCD。

参照系检索本体在独立仓 `fd-zhesi-reference`（MCP 服务），本仓不承载参照系实现——照 fd-lex 与 fd-legal-search-mcp 的分仓先例。

## 骨架期口径

- web 三入口均为真实可渲染占位页（task 6.2 落三闭环界面）
- server 提供 `/healthz`、`/api/version`；个人层 API 挂载点 task 3.x
- 隐私立场：个人层是用户信念记录，只落本仓自有存储，不进共享底座（spec「个人层私有归属」）

## 本地开发

web：`cd web && npm install && npm run dev`
server：`cd server && pip install -e ".[dev]" && pytest && uvicorn fd_zhesi_api.main:app --port 8010`

## 目录

```
web/      三入口前端（/ 官网、/workbench 工作台、/admin 后台），React 19 + Vite + TS
server/   FastAPI 个人层服务：立场卡 / 张力簿 / 思想年轮的自有存储
openspec/ 本仓的规格根（能力与变更就地治理）
```

## 与兄弟仓的关系

参照系检索（本体的 MCP 服务）在 `fd-zhesi-reference`，本仓不承载它。
这条分仓先例照 `fd-lex` 与 `fd-legal-search-mcp`：门面与检索本体各自成仓、
各自发布，门面通过 HTTP 契约访问检索面，不 import 对方代码。

## 当前状态

骨架期：三个入口都是真实可渲染的占位页，`/healthz` 与 `/api/version` 已通，
个人层的 API 挂载点（立场卡/张力簿/思想年轮）随 task 3.x 落。上线后跑在
cheap 的 `fd-prod`，镜像走 TCR，部署清单在 `fd-infra-deploy`（本仓不放清单）。
