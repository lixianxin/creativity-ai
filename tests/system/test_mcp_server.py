# -*- coding: utf-8 -*-
"""MCP Server 离线验收：8 个工具经内存会话真实调用 + 1 条 stdio 子进程冒烟。

零网络、零密钥：RunStore 用 tmp_path SQLite；不触发任何 LLM 路径。
内存会话用 anyio 任务组常驻 server 协程，用例本身保持同步（不引 pytest-asyncio）。
"""
import asyncio
import json
import os
import sys
from pathlib import Path

import anyio
import pytest

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.memory import create_client_server_memory_streams

from agents.registry import registry
from core.run_store import RunStore
from mcp_server.server import mcp as _server

ROOT = Path(__file__).resolve().parents[2]
RUN_ID = "run_test01"
TOOL_NAMES = [
    "get_agent_runs", "get_dag", "get_ready_set", "get_run",
    "list_agents", "list_runs", "read_report", "validate_report",
]


def _with_session(fn):
    """经内存流真起 server，把已握手的 ClientSession 交给 fn，返回其结果。"""
    async def _run():
        async with create_client_server_memory_streams() as ((c_read, c_write), (s_read, s_write)):
            async with ClientSession(c_read, c_write) as session:
                async with anyio.create_task_group() as tg:
                    tg.start_soon(
                        _server._lowlevel_server.run,
                        s_read, s_write,
                        _server._lowlevel_server.create_initialization_options(),
                    )
                    await session.initialize()
                    try:
                        return await fn(session)
                    finally:
                        tg.cancel_scope.cancel()
    return asyncio.run(_run())


def _call(tool, args=None):
    async def _go(session):
        result = await session.call_tool(tool, args or {})
        assert not result.is_error, f"{tool} 返回协议级错误: {result.content}"
        return json.loads("".join(c.text for c in result.content))
    return _with_session(_go)


@pytest.fixture()
def store_env(tmp_path):
    """临时 SQLite 库 + 混合图态 Run：user_insight=success、finance=failed、其余 queued。"""
    db_path = tmp_path / "runs.db"
    store = RunStore(db_path=str(db_path))
    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    store.create_run(
        "面向大学生的 AI 简历诊断工具",
        registry.stage_specs_tuples(),
        report_dir=str(report_dir),
        run_id=RUN_ID,
    )
    report = report_dir / "01_user.md"  # 命名规则与 orchestrator 一致：{seq}_{stage_key}.md
    report.write_text("# 用户洞察报告\n\n目标用户为高校创业者，痛点真实存在。" * 20, encoding="utf-8")
    store.finish_agent(RUN_ID, "user_insight", "success", output_path=str(report))
    store.finish_agent(RUN_ID, "finance", "failed", error="模拟 API 限流")
    return {"db": str(db_path), "report_text": report.read_text(encoding="utf-8")}


def test_list_tools_registers_eight():
    tools = _with_session(lambda session: session.list_tools())
    names = sorted(t.name for t in tools.tools)
    assert len(names) == 8
    assert names == sorted(TOOL_NAMES)


def test_list_agents():
    payload = _call("list_agents")
    assert payload["count"] == 12
    assert payload["agents"][0]["name"] == "user_insight"
    commander = next(a for a in payload["agents"] if a["name"] == "commander")
    assert commander["dependencies"] == ["risk_review", "red_team"]
    assert len(commander["soft_dependencies"]) == 7


def test_get_dag():
    payload = _call("get_dag")
    assert payload["layer_count"] == 5
    assert payload["layer_sizes"] == [8, 1, 1, 1, 1]
    assert "risk_review" in payload["layers"][0]
    kinds = {e["kind"] for e in payload["edges"]}
    assert kinds == {"hard", "soft"}
    assert payload["edge_count"] == 18  # 7 hard（commander2+review3+pitch2）+ 11 soft（红队4+总指挥7）


def test_list_runs_and_get_run(store_env):
    payload = _call("list_runs", {"db_path": store_env["db"]})
    assert payload["count"] == 1
    assert payload["runs"][0]["run_id"] == RUN_ID

    detail = _call("get_run", {"run_id": RUN_ID, "db_path": store_env["db"]})
    assert detail["run"]["status"] == "queued"
    assert detail["run"]["project_input"] == "面向大学生的 AI 简历诊断工具"

    missing = _call("get_run", {"run_id": "run_nope", "db_path": store_env["db"]})
    assert missing["error"]["code"] == "RUN_NOT_FOUND"


def test_get_agent_runs(store_env):
    payload = _call("get_agent_runs", {"run_id": RUN_ID, "db_path": store_env["db"]})
    assert payload["count"] == 12
    by_name = {a["agent_name"]: a for a in payload["agent_runs"]}
    assert by_name["user_insight"]["status"] == "success"
    assert by_name["finance"]["status"] == "failed"

    missing = _call("get_agent_runs", {"run_id": "run_nope", "db_path": store_env["db"]})
    assert missing["error"]["code"] == "RUN_NOT_FOUND"


def test_read_report(store_env):
    payload = _call("read_report", {
        "run_id": RUN_ID, "agent_name": "user_insight", "db_path": store_env["db"],
    })
    assert payload["content"] == store_env["report_text"]
    assert payload["chars"] == len(store_env["report_text"])

    unknown_agent = _call("read_report", {
        "run_id": RUN_ID, "agent_name": "not_an_agent", "db_path": store_env["db"],
    })
    assert unknown_agent["error"]["code"] == "AGENT_NOT_FOUND"

    no_file = _call("read_report", {
        "run_id": RUN_ID, "agent_name": "market_analysis", "db_path": store_env["db"],
    })
    assert no_file["error"]["code"] == "REPORT_NOT_FOUND"

    unknown_run = _call("read_report", {
        "run_id": "run_nope", "agent_name": "user_insight", "db_path": store_env["db"],
    })
    assert unknown_run["error"]["code"] == "RUN_NOT_FOUND"


def test_validate_report():
    empty = _call("validate_report", {"agent_name": "user_insight", "report_text": ""})
    assert empty["accepted"] is False
    assert "EMPTY_OUTPUT" in {i["code"] for i in empty["issues"]}
    assert empty["needs_repair"] is True
    assert empty["known_agent"] is True

    long_text = "这是一份内容足够长的测试报告，包含若干分析与结论段落。" * 20
    ok = _call("validate_report", {"agent_name": "mystery_agent", "report_text": long_text})
    assert ok["accepted"] is True
    assert ok["known_agent"] is False  # 未知 Agent 只跑通用闸门，不报错


def test_get_ready_set(store_env):
    payload = _call("get_ready_set", {"run_id": RUN_ID, "db_path": store_env["db"]})
    ready_names = [r["name"] for r in payload["ready"]]
    assert ready_names == [
        "market_analysis", "competitor_analysis", "product_design",
        "business_model", "growth_ops", "risk_review",
    ]
    assert payload["snapshot"]["success"] == ["user_insight"]
    assert "finance" in payload["snapshot"]["failed"]
    assert len(payload["snapshot"]["pending"]) == 4  # 红队/总指挥/评审/答辩


def test_require_exists_db_guard():
    missing = _call("list_runs", {
        "db_path": str(ROOT / "data" / "definitely_missing.db"), "require_exists": True,
    })
    assert missing["error"]["code"] == "DB_NOT_FOUND"


def test_stdio_subprocess_smoke():
    """真实 stdio 传输：子进程起 python -m mcp_server，握手并调用一次。"""
    async def _run():
        params = StdioServerParameters(
            command=sys.executable, args=["-m", "mcp_server"], cwd=str(ROOT),
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("list_agents", {})
                return json.loads("".join(c.text for c in result.content))

    payload = asyncio.run(_run())
    assert payload["count"] == 12
    assert len(payload["agents"]) == 12
