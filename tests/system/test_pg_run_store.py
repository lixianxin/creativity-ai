# -*- coding: utf-8 -*-
"""RunStore PG 后端验收（需 SUPABASE_DB_URL；未配置自动 SKIP，零成本）。

覆盖（纯 store 操作，不调 LLM）：
1. user_id 自动回填：create_run 未显式传时取 store 构造绑定的 user_id；
2. PG 往返：create → start_agent → finish_agent → get_resume_plan →
   resume_run → finish_run，字段 / JSONB / 时间戳往返一致；
3. RLS 双用户隔离：用户 B 对用户 A 的 Run 完全不可见、不可改——
   即使 WHERE 条件写错（如查 A 的 user_id）也返回空，越权 UPDATE 影响 0 行；
4. list_user_runs 归属过滤。

运行方式：配置 SUPABASE_DB_URL 环境变量（或 .streamlit/secrets.toml 后由
app.py 注入环境）后执行 `python tests/system/test_pg_run_store.py`。
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main() -> int:
    dsn = os.environ.get("SUPABASE_DB_URL")
    if not dsn:
        print("SKIP: 未配置 SUPABASE_DB_URL，PG 验收跳过（SQLite 回归不受影响）")
        return 0

    from core.run_store import RunStore

    USER_A = "aaaaaaaa-1111-2222-3333-444444444444"
    USER_B = "bbbbbbbb-1111-2222-3333-444444444444"
    SPECS = [("1", "idea_validate", "用户洞察官", "用户洞察")]

    # ── 1. user_id 自动回填 ──
    store_a = RunStore(user_id=USER_A)
    run = store_a.create_run("PG 验收项目", SPECS)
    row = store_a.get_run(run.run_id)
    assert row and row.user_id == USER_A, f"user_id 未回填: {row and row.user_id}"
    ar = {a.agent_name: a for a in store_a.list_agent_runs(run.run_id)}["用户洞察官"]
    assert ar.stage_key == "idea_validate" and ar.status == "queued"
    print("  [1] user_id 自动回填 OK")

    # ── 2. PG 往返 ──
    store_a.start_agent(run.run_id, "用户洞察官")
    ar = {a.agent_name: a for a in store_a.list_agent_runs(run.run_id)}["用户洞察官"]
    assert ar.status == "running" and isinstance(ar.started_at, str), ar
    store_a.finish_agent(
        run.run_id, "用户洞察官", "success",
        conclusion="委员会结论", output_path="reports/demo.md",
        validation={"issues": [], "ok": True}, metadata={"elapsed_s": 1.5},
    )
    ar = {a.agent_name: a for a in store_a.list_agent_runs(run.run_id)}["用户洞察官"]
    assert ar.status == "success" and ar.conclusion == "委员会结论"
    assert ar.validation == {"issues": [], "ok": True} and ar.metadata == {"elapsed_s": 1.5}
    plan = store_a.get_resume_plan(run.run_id)
    assert len(plan["succeeded"]) == 1 and not plan["pending"]
    # 暂停 → 恢复 往返（running 态直接 resume 会被拒，pause 后合法）
    store_a.pause_run(run.run_id, "测试暂停")
    assert store_a.get_run(run.run_id).status == "paused"
    store_a.resume_run(run.run_id)
    assert store_a.get_run(run.run_id).status == "running"
    store_a.finish_run(run.run_id, success_count=1, fail_count=0)
    assert store_a.get_run(run.run_id).status == "success"
    assert store_a.get_run(run.run_id).finished_at is not None
    print("  [2] PG 往返（checkpoint / JSONB / 时间戳归一）OK")

    # ── 3. RLS 双用户隔离 ──
    store_b = RunStore(user_id=USER_B)
    assert store_b.get_run(run.run_id) is None, "B 不应能看到 A 的 Run"
    assert store_b.list_user_runs(USER_A) == [], "WHERE 漏写也查不到 A 的数据"
    try:
        store_b.get_resume_plan(run.run_id)
        raise AssertionError("B 不应能拿到 A 的恢复计划")
    except ValueError:
        pass
    store_b.finish_agent(run.run_id, "用户洞察官", "failed", error="越权尝试")
    ar = {a.agent_name: a for a in store_a.list_agent_runs(run.run_id)}["用户洞察官"]
    assert ar.status == "success" and ar.error == "", "B 的越权 UPDATE 影响 0 行"
    print("  [3] RLS 双用户隔离（读不到 / 计划拿不到 / 改不动）OK")

    # ── 4. list_user_runs 归属过滤 ──
    runs_a = store_a.list_user_runs(USER_A)
    assert any(r.run_id == run.run_id for r in runs_a)
    assert all(r.user_id == USER_A for r in runs_a)
    print("  [4] list_user_runs 归属过滤 OK")

    print("PG RunStore 验收：4/4 通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
