# -*- coding: utf-8 -*-
"""tests/system 的 pytest 收集配置。

历史离线验收脚本（test_phase_7_*.py / test_v2_runtime.py）内部用例之间存在
返回值传递（如 test_d 依赖 test_b 产出的 db_path/rid），不能被 pytest 当作
独立用例逐条收集；它们由 test_offline_suites.py 以子进程方式整条复跑，
与 README 中 `python tests/system/test_xxx.py` 的文档命令完全等价。

test_pg_run_store.py / audit_rls.py 需要真实 SUPABASE_DB_URL（门控），
不属于离线 CI 范围，也保持独立运行。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

collect_ignore = [
    "test_phase_7_6_acceptance.py",
    "test_phase_7_7_dag.py",
    "test_phase_7_8_critic_repair.py",
    "test_phase_7_9_validator_semantics.py",
    "test_v2_runtime.py",
    "test_pg_run_store.py",
    "audit_rls.py",
]
