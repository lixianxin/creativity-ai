# -*- coding: utf-8 -*-
"""创想∞ AI创业委员会 MCP Server：把平台确定性能力以 MCP 协议暴露为标准工具。

8 个工具全部只读、免 LLM、免密钥，复用现有单一事实源：
  Registry / ExecutionPlanner（DAG）· RunStore（运行记录与报告）· ResultValidator（确定性校验）

启动（stdio transport，MCP 客户端经 stdin/stdout 通信）：
    python -m mcp_server

目标数据库解析顺序：工具参数 db_path > 环境变量 CREATIVITY_MCP_DB > RunStore 默认路径
（SUPABASE_DB_URL 存在时走 PostgreSQL，否则本地 SQLite data/creativity_runs.db）。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from mcp.server.mcpserver import MCPServer

from agents.registry import registry
from core.execution_graph import ExecutionPlanner
from core.result_validator import validate_result
from core.run_store import RunStore
from schemas.agent_result import AgentResult

mcp = MCPServer(
    "creativity-ai-committee",
    instructions=(
        "创想∞ AI创业委员会：12 Agent 多智能体创业诊断平台的确定性能力集合。"
        "全部工具只读、免 LLM：DAG 结构、运行历史、报告正文、输出校验、就绪集结算。"
    ),
)

# 领域性"查无此物"错误码（对齐项目失败分类口径：结构化返回，isError=false）
ERR_RUN_NOT_FOUND = "RUN_NOT_FOUND"
ERR_AGENT_NOT_FOUND = "AGENT_NOT_FOUND"
ERR_REPORT_NOT_FOUND = "REPORT_NOT_FOUND"
ERR_DB_NOT_FOUND = "DB_NOT_FOUND"


def _error(code: str, message: str) -> Dict[str, Any]:
    return {"error": {"code": code, "message": message}}


def _open_store(db_path: str, require_exists: bool) -> Tuple[Optional[RunStore], Optional[Dict[str, Any]]]:
    """解析目标 RunStore；失败时返回 (None, 结构化错误)。"""
    path = db_path or os.environ.get("CREATIVITY_MCP_DB", "")
    if path:
        if require_exists and not Path(path).exists():
            return None, _error(ERR_DB_NOT_FOUND, f"数据库文件不存在: {path}")
        return RunStore(db_path=path), None
    return RunStore(), None


def _spec_to_dict(spec) -> Dict[str, Any]:
    return {
        "name": spec.name,
        "seq": spec.seq,
        "stage_key": spec.stage_key,
        "label": spec.label,
        "group": spec.group,
        "dependencies": list(spec.dependencies),
        "soft_dependencies": list(spec.soft_dependencies),
        "capabilities": list(spec.capabilities),
    }


@mcp.tool()
def list_agents() -> Dict[str, Any]:
    """列出委员会全部 12 个 Agent 的 AgentSpec（硬/软依赖声明，Registry 单一事实源）。"""
    agents = [_spec_to_dict(s) for s in registry.all()]
    return {"agents": agents, "count": len(agents)}


@mcp.tool()
def get_dag() -> Dict[str, Any]:
    """返回 12 Agent 依赖 DAG 的 Kahn 拓扑分层与全部依赖边（hard/soft）。"""
    planner = ExecutionPlanner(registry.all())
    layers = [[s.name for s in layer] for layer in planner.layers]
    edges = [
        {"upstream": upstream, "downstream": downstream, "kind": kind}
        for upstream, downstream, kind in planner.describe_edges()
    ]
    return {
        "layers": layers,
        "layer_count": len(layers),
        "layer_sizes": [len(layer) for layer in layers],
        "edges": edges,
        "edge_count": len(edges),
    }


@mcp.tool()
def list_runs(limit: int = 10, db_path: str = "", require_exists: bool = False) -> Dict[str, Any]:
    """列出最近的诊断 Run（RunStore 只读，按创建时间倒序）。"""
    store, err = _open_store(db_path, require_exists)
    if err:
        return err
    runs = [r.to_dict() for r in store.list_recent_runs(limit)]
    return {"runs": runs, "count": len(runs)}


@mcp.tool()
def get_run(run_id: str, db_path: str = "", require_exists: bool = False) -> Dict[str, Any]:
    """读取单条 Run 的状态与元数据。"""
    store, err = _open_store(db_path, require_exists)
    if err:
        return err
    run = store.get_run(run_id)
    if run is None:
        return _error(ERR_RUN_NOT_FOUND, f"Run 不存在: {run_id}")
    return {"run": run.to_dict()}


@mcp.tool()
def get_agent_runs(run_id: str, db_path: str = "", require_exists: bool = False) -> Dict[str, Any]:
    """读取某次 Run 全部 12 棒的 checkpoint 记录（agent_runs 表）。"""
    store, err = _open_store(db_path, require_exists)
    if err:
        return err
    if store.get_run(run_id) is None:
        return _error(ERR_RUN_NOT_FOUND, f"Run 不存在: {run_id}")
    agent_runs = [a.to_dict() for a in store.list_agent_runs(run_id)]
    return {"run_id": run_id, "agent_runs": agent_runs, "count": len(agent_runs)}


@mcp.tool()
def read_report(run_id: str, agent_name: str, db_path: str = "", require_exists: bool = False) -> Dict[str, Any]:
    """读取某棒报告正文（文件系统；output_path 优先，report_dir 按命名规则兜底）。"""
    store, err = _open_store(db_path, require_exists)
    if err:
        return err
    if not registry.has(agent_name):
        return _error(ERR_AGENT_NOT_FOUND, f"未注册的 Agent: {agent_name}")
    run = store.get_run(run_id)
    if run is None:
        return _error(ERR_RUN_NOT_FOUND, f"Run 不存在: {run_id}")
    agent_run = next(
        (a for a in store.list_agent_runs(run_id) if a.agent_name == agent_name), None
    )
    if agent_run is None:
        return _error(ERR_AGENT_NOT_FOUND, f"Run {run_id} 中无 Agent 记录: {agent_name}")

    candidates = []
    if agent_run.output_path:
        candidates.append(Path(agent_run.output_path))
    spec = registry.get(agent_name)
    if run.report_dir:
        # 与 orchestrator 一致的命名规则：{seq}_{stage_key}.md
        candidates.append(Path(run.report_dir) / f"{spec.seq}_{spec.stage_key}.md")

    for path in candidates:
        if path.is_file():
            content = path.read_text(encoding="utf-8")
            return {
                "run_id": run_id,
                "agent_name": agent_name,
                "path": str(path),
                "content": content,
                "chars": len(content),
            }
    tried = [str(c) for c in candidates]
    return _error(ERR_REPORT_NOT_FOUND, f"报告文件不存在（agent={agent_name}，已尝试 {tried}）")


@mcp.tool()
def validate_report(agent_name: str, report_text: str) -> Dict[str, Any]:
    """用确定性 Validator 校验报告文本（与审议链路同一套规则；未知 Agent 只跑通用闸门）。"""
    result = AgentResult(agent_name=agent_name, raw_output=report_text)
    vr = validate_result(result)
    out = vr.to_dict()
    out["needs_repair"] = vr.needs_repair
    out["known_agent"] = registry.has(agent_name)
    return out


@mcp.tool()
def get_ready_set(run_id: str, db_path: str = "", require_exists: bool = False) -> Dict[str, Any]:
    """按 Run 当前图状态重算就绪集与九分类图快照（与 resume 同一结算逻辑）。"""
    store, err = _open_store(db_path, require_exists)
    if err:
        return err
    if store.get_run(run_id) is None:
        return _error(ERR_RUN_NOT_FOUND, f"Run 不存在: {run_id}")
    states = store.agent_states(run_id)
    planner = ExecutionPlanner(registry.all())
    ready = [
        {
            "name": spec.name,
            "label": spec.label,
            "seq": spec.seq,
            "degraded_inputs": sorted(degraded),
        }
        for spec, degraded in planner.ready_set(states)
    ]
    return {
        "run_id": run_id,
        "ready": ready,
        "snapshot": planner.graph_snapshot(states),
    }


def main() -> None:
    mcp.run()  # 默认 stdio transport


if __name__ == "__main__":
    main()
