"""能力快照自查（llm.model_verdict）的测试。

锁四件事：
  1. 任何失败都必须 checked=False（→ 调用行为不变），不许抛
  2. serving / permitted_only / 都看不到 —— 三种诊断必须可区分
  3. 大小写与形状（dict 或裸字符串）都要吃
  4. key 与 token 绝不出现在返回结构里

契约：paas/openspec/changes/add-ciyuan-capability-contract/specs/ciyuan-capability-endpoint/spec.md
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from fd_zhesi_api import llm

SCHEMA = "ciyuan.capabilities/v1"


class _Stub(BaseHTTPRequestHandler):
    """最小能力快照桩：由类属性 payload / status 控制响应。"""

    payload: dict | None = None
    status: int = 200

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/v1/ciyuan/capabilities":
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps(self.payload if self.payload is not None else {}).encode()
        self.send_response(self.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:  # 静音
        return


@pytest.fixture()
def gateway(monkeypatch):
    """起一个本地桩网关，把 base URL 与 key 指过去。

    _Stub 的 payload/status 是类属性，必须每个用例复位——否则前一个用例设的
    404/503 会漏给下一个，表现为「单独跑绿、连跑红」的假失败。
    """
    _Stub.payload = None
    _Stub.status = 200
    server = HTTPServer(("127.0.0.1", 0), _Stub)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    monkeypatch.setenv("FD_ZHESI_LLM_BASE_URL", f"http://127.0.0.1:{port}/v1")
    monkeypatch.setenv("FD_ZHESI_LLM_API_KEY", "sk-test-should-never-leak")
    monkeypatch.delenv("FD_ZHESI_LLM_MODEL", raising=False)
    yield _Stub
    server.shutdown()
    thread.join(timeout=5)


def _snapshot(serving=(), permitted_only=()):
    return {
        "schema": SCHEMA,
        "generated_at": "2026-11-10T15:00:00Z",
        "basis": "schedulable_account_config",
        "probed": False,
        "models": {
            "serving": [{"id": m, "kind": "unknown"} for m in serving],
            "permitted_only": [{"id": m, "kind": "unknown", "basis": "allowlist"} for m in permitted_only],
            "counts": {"serving": len(serving), "permitted_only": len(permitted_only)},
        },
        "lanes": {},
        "media": {},
        "limits": {},
    }


# ── 1. 三种诊断可区分 ─────────────────────────────────────

def test_default_model_in_serving(gateway, monkeypatch):
    gateway.payload = _snapshot(serving=["gpt-5.4-mini", "deepseek-v4.1-flash"])
    monkeypatch.setenv("FD_ZHESI_LLM_MODEL", "gpt-5.4-mini")

    v = llm.model_verdict()

    assert v["checked"] is True
    assert v["in_serving"] is True
    assert v["in_permitted_only"] is False
    assert v["serving_count"] == 2
    assert "可正常服务" in v["note"]


def test_default_model_only_permitted(gateway, monkeypatch):
    # 白名单放行、但没有可调度账号能服务 —— 真实调用会失败的那种
    gateway.payload = _snapshot(serving=["other-model"], permitted_only=["gpt-5.4-mini"])
    monkeypatch.setenv("FD_ZHESI_LLM_MODEL", "gpt-5.4-mini")

    v = llm.model_verdict()

    assert v["checked"] is True
    assert v["in_serving"] is False
    assert v["in_permitted_only"] is True
    assert "permitted_only" in v["note"]


def test_default_model_unknown_to_key(gateway, monkeypatch):
    # id 形状漂移的典型症状：服务端换了名字，这边还写着旧名
    gateway.payload = _snapshot(serving=["deepseek-v4.1-flash"])
    monkeypatch.setenv("FD_ZHESI_LLM_MODEL", "gpt-5.4-mini")

    v = llm.model_verdict()

    assert v["checked"] is True
    assert v["in_serving"] is False
    assert v["in_permitted_only"] is False
    assert "看不到它" in v["note"]
    assert v["suggestions"] == ["deepseek-v4.1-flash"]


# ── 2. 一切失败都 checked=False ────────────────────────────

def test_no_key_skips_entirely(monkeypatch):
    monkeypatch.delenv("FD_ZHESI_LLM_API_KEY", raising=False)
    v = llm.model_verdict()
    assert v["checked"] is False
    assert v["in_serving"] is None
    assert "调用行为不受影响" in v["note"]


def test_endpoint_missing_404(gateway):
    gateway.payload = None
    gateway.status = 404
    v = llm.model_verdict()
    assert v["checked"] is False
    assert v["in_serving"] is None


def test_endpoint_503(gateway):
    gateway.payload = {"error": {"type": "lane_upstream_unavailable"}}
    gateway.status = 503
    v = llm.model_verdict()
    assert v["checked"] is False


def test_schema_mismatch_rejected(gateway):
    gateway.payload = _snapshot(serving=["m"])
    gateway.payload["schema"] = "other/v9"
    v = llm.model_verdict()
    assert v["checked"] is False, "schema 不符不许当成 v1 用"


def test_malformed_models_rejected(gateway):
    gateway.payload = {"schema": SCHEMA, "models": {"serving": "nope"}}
    v = llm.model_verdict()
    assert v["checked"] is False


def test_unreachable_gateway(monkeypatch):
    monkeypatch.setenv("FD_ZHESI_LLM_API_KEY", "sk-x")
    monkeypatch.setenv("FD_ZHESI_LLM_BASE_URL", "http://127.0.0.1:1/v1")  # 必然拒绝
    v = llm.model_verdict(timeout=0.5)
    assert v["checked"] is False


# ── 3. 形状与大小写 ───────────────────────────────────────

def test_accepts_bare_string_ids_and_case_insensitive(gateway, monkeypatch):
    gateway.payload = {
        "schema": SCHEMA,
        "models": {"serving": ["GPT-5.4-Mini"], "permitted_only": []},
    }
    monkeypatch.setenv("FD_ZHESI_LLM_MODEL", "gpt-5.4-mini")
    v = llm.model_verdict()
    assert v["checked"] is True
    assert v["in_serving"] is True


# ── 4. 不泄露 ─────────────────────────────────────────────

def test_key_never_appears_in_verdict(gateway, monkeypatch):
    gateway.payload = _snapshot(serving=["m"])
    v = llm.model_verdict()
    blob = json.dumps(v, ensure_ascii=False)
    assert "sk-test-should-never-leak" not in blob
    assert "Bearer" not in blob


# ── 5. CLI 入口 ───────────────────────────────────────────

def test_cli_requires_flag(capsys):
    assert llm.main([]) == 2
    assert "--check-model" in capsys.readouterr().err


def test_cli_prints_json(gateway, monkeypatch, capsys):
    gateway.payload = _snapshot(serving=["gpt-5.4-mini"])
    monkeypatch.setenv("FD_ZHESI_LLM_MODEL", "gpt-5.4-mini")

    assert llm.main(["--check-model"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["checked"] is True
    assert out["in_serving"] is True
