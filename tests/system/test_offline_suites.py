# -*- coding: utf-8 -*-
"""离线套件的 pytest 入口：一条命令复跑全部离线验收脚本。

设计说明：
- 5 个脚本以**子进程**运行，与文档命令 `python tests/system/test_xxx.py`
  完全等价；脚本仍可脱离 pytest 独立运行，双重入口并存。
- 全部离线：不触网、不调用真实 LLM、不需要任何密钥（SQLite 临时库）。
- 需要真实 API 的脚本（phase_7_*_real_run.py / smoke_auth.py）不叫
  test_ 前缀，pytest 天然不收集，绝不进入 CI。
- PG 门控测试（test_pg_run_store.py）需 SUPABASE_DB_URL，在 conftest 中
  排除收集；CI 不配置该密钥时它不会运行。
"""
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent

# (用例 ID, 脚本, 套件说明)
SUITES = [
    ("runtime_acceptance_56", "test_phase_7_6_acceptance.py",
     "Phase 7-6 运行时验收（checkpoint/resume/失败路径，56 项断言）"),
    ("dag_52", "test_phase_7_7_dag.py",
     "Phase 7-7 DAG 调度（并行/硬软依赖/阻断/恢复，52 项断言）"),
    ("critic_repair_39", "test_phase_7_8_critic_repair.py",
     "Phase 7-8 Critic/Repair 闭环（39 项断言）"),
    ("validator_semantics_36", "test_phase_7_9_validator_semantics.py",
     "Phase 7-9 Validator 语义（36 项断言）"),
    ("runtime_failure_paths_80", "test_v2_runtime.py",
     "V2 Runtime 失败分类/错误差异化/断点恢复（80 项断言）"),
]


@pytest.mark.parametrize(
    "script,desc",
    [(s, d) for _, s, d in SUITES],
    ids=[sid for sid, _, _ in SUITES],
)
def test_offline_suite(script, desc):
    proc = subprocess.run(
        [sys.executable, str(HERE / script)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    print(f"\n----- {desc} -----")
    print(output)
    assert proc.returncode == 0, f"{script} 退出码 {proc.returncode}，见上方输出"
