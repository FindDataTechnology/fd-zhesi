# 哲思（zhesi）公网接入：SafeLine + 证书配置单

> 日期：2026-10-21 ／ 写给：在远程机器上操作雷池与证书的运维
> 对应服务已在 cheap 集群 fd-prod 运行（ArgoCD 管理），本文只需在雷池侧完成接入。

## 1. 需要暴露什么（只有一个站点要建）

| 项 | 值 |
|---|---|
| 建议域名 | `zhesi.finddatatech.cloud`（与 lex./wire./platform. 同族；若已有 `*.finddatatech.cloud` 泛域名证书可直接用） |
| 回源地址 | `http://100.64.0.8:31901`（fd-zhesi-web，NodePort，任一 cheap 节点均可回源：100.64.0.8 / .9 / .13 / .14 / .15） |
| 回源协议 | HTTP（集群内无 TLS），对外 HTTPS + HTTP→HTTPS 跳转 |
| 说明 | **只需要这一个站点**。API（fd-zhesi-api）不需要单独暴露——web 的 nginx 已把 `/api/` 反代到集群内 api 服务；参照系 MCP（31900）走内网，不直接上公网（见 §4） |

## 2. 站点行为要点

- **上游健康检查**：`GET /healthz` 期待 200（nginx 直接回 `ok`，无依赖）。
- **不要缓存 `index.html`**：SPA（React），发版后必须拿到新 hash 的资源文件名；js/css 带 7 天缓存指纹无妨。
- **超时**：`/api/` 有 LLM 调用，回源读超时请 ≥ 60s（web→api 反代已设 60s，雷池侧别低于它）。

## 3. 雷池已知坑（家族实测，务必处理）

1. **拦截含代码/脚本片段的 POST body**（壹座市场 pack 安装被拦的同款问题）：
   `/api/v1/ask`、`/api/v1/debate/*`、`/api/v1/contract/*` 的 JSON 请求体里可能含哲学引文、
   反驳论证文本（引号/连字符密集）。请对路径 `^/api/` 的 POST 做放行（白名单规则）或把
   该站点 body 检测降级，否则问/辩闭环会被误拦。
2. **Bearer 头**：所有 `/api/` 调用带 `Authorization: Bearer <JWT>`，请确认雷池不剥这个头。
3. **SPA 强制重载**（wire 四屏的教训）：如果页面出不来，先硬刷新（Cmd+Shift+R）再排障，
   避免把缓存问题误判成服务问题。

## 4. 参照系 MCP（31900）如何上公网——不建直连站点

`fd-zhesi-reference`（NodePort 31900，`/mcp` 端点，streamable-http/SSE）**建议走既有
mcp 网关注册通道**（`mcp.finddatatech.cloud/fd-zhesi-reference`，同 fd-legal-search-mcp
的 registry 模式），而不是在雷池单开站点——网关侧已处理 MCP 的会话/路由语义。
若确要直连暴露，雷池必须满足：

- `proxy_buffering off`（SSE 流式响应不能缓冲）
- 读超时 ≥ 120s；HTTP/1.1；放行 `mcp-session-id` 响应头
- 回源 `http://100.64.0.8:31900`

## 5. 证书

- 单域名 `zhesi.finddatatech.cloud` 或复用泛域名 `*.finddatatech.cloud` 均可；
- 证书装在雷池侧即可，集群内全部 HTTP 回源，无需改任何 manifest。

## 6. 接入后验收清单（按序 curl）

```bash
# 1) 站点通 + SPA 渲染
curl -s https://zhesi.finddatatech.cloud/healthz          # -> ok
curl -s https://zhesi.finddatatech.cloud/ | grep -o '<title>.*</title>'   # -> 哲思 Zhesi

# 2) 鉴权边界（应 401，证明 /api/ 反代与 Bearer 头未被剥）
curl -s -o /dev/null -w '%{http_code}\n' -X POST \
  https://zhesi.finddatatech.cloud/api/v1/ask \
  -H 'Content-Type: application/json' -d '{"text":"test"}'   # -> 401

# 3) （有真实 Logto JWT 后）全链：ask -> 建卡 -> 辩 -> 投影
```

4) 最后浏览器打开 `https://zhesi.finddatatech.cloud/workbench`：右上角令牌框输入
JWT 后三 tab（问/辩/谱）应可用；未配引擎时显示「该能力接线中」属正常降级。

## 7. 现状备注

- Logto SPA 登录流尚未做（现为开发态令牌输入）；JWKS 校验已在服务端就绪
  （`FD_ZHESI_AUTH_JWKS=https://auth.finddatatech.cloud/oidc/jwks`），
  有效 Logto JWT 即可直通生产。
- 服务端 CORS 当前全开（骨架期惯例），域名定了之后建议收敛到该 origin。
