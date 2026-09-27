# -*- coding: utf-8 -*-
"""RLS 数据库层审计：策略状态 + 角色属性 + 双会话越权实测。只读 + 假数据自清。"""
import sys
import tomllib
from pathlib import Path

import psycopg2

ROOT = Path(__file__).resolve().parents[2]
secrets = tomllib.load(open(ROOT / ".streamlit" / "secrets.toml", "rb"))
APP_DSN = secrets["SUPABASE_DB_URL"]


def section(title):
    print(f"\n=== {title} ===")


section("0. 冲刷连接池（清除历史误留的会话级 app.user_id）")
import threading


def scrub_backends(dsn, n=10):
    """并发钉住 n 个后端：置空会话级 GUC，返回本轮发现的污染数。"""
    found = []
    conns = [psycopg2.connect(dsn, connect_timeout=20) for _ in range(n)]

    def work(i, conn):
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("SELECT current_setting('app.user_id', true)")
        v = cur.fetchone()[0]
        if v:
            found.append((i, v[:8]))
        cur.execute("SELECT set_config('app.user_id', NULL, false)")
        cur.execute("DISCARD ALL")

    threads = [threading.Thread(target=work, args=(i, cc)) for i, cc in enumerate(conns)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    for cc in conns:
        cc.close()
    return found


polluted = scrub_backends(APP_DSN) + scrub_backends(APP_DSN)
print(f"  两轮各钉 10 后端，发现污染 {len(polluted)} 个: {polluted}")

# 验证：再钉 10 个全新后端，必须全部读不到会话变量
conns = [psycopg2.connect(APP_DSN, connect_timeout=20) for _ in range(10)]
leftover = []


def check(conn):
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SELECT current_setting('app.user_id', true)")
    v = cur.fetchone()[0]
    if v:  # 仅非空 UUID 才算污染；NULL/'' 都是安全空身份
        leftover.append(v)


threads = [threading.Thread(target=check, args=(cc,)) for cc in conns]
for t in threads:
    t.start()
for t in threads:
    t.join()
for cc in conns:
    cc.close()
assert not leftover, f"仍有后端携带非空会话 GUC: {leftover}"
print("  第三轮 10 后端无非空会话残留（空身份由策略 NULLIF 闸兜底）")

# 1) RLS 开关与 FORCE 状态（以应用角色读系统视图）
c = psycopg2.connect(APP_DSN, connect_timeout=20)
cur = c.cursor()
section("1. 表级 RLS 状态")
cur.execute(
    "SELECT c.relname, c.relrowsecurity AS rls_enabled, c.relforcerowsecurity AS rls_forced "
    "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
    "WHERE n.nspname='public' AND c.relname IN ('runs','agent_runs') ORDER BY c.relname"
)
for name, enabled, forced in cur.fetchall():
    flag = "OK" if enabled and forced else "FAIL"
    print(f"  [{flag}] {name}: enabled={enabled} forced={forced}")

# 2) 策略定义
section("2. RLS 策略")
cur.execute(
    "SELECT tablename, policyname, cmd, roles, qual, with_check "
    "FROM pg_policies WHERE schemaname='public' ORDER BY tablename"
)
rows = cur.fetchall()
for t, p, cmd, roles, qual, wc in rows:
    print(f"  table={t} policy={p} cmd={cmd} roles={roles}")
    print(f"    USING: {qual}")
    print(f"    CHECK: {wc}")
assert len(rows) >= 2, "策略缺失"
c.close()

# 3) 应用角色特权属性
c = psycopg2.connect(APP_DSN, connect_timeout=20)
cur = c.cursor()
section("3. runstore_app 角色特权（三项必须全 false）")
cur.execute(
    "SELECT rolsuper, rolcreaterole, rolbypassrls, rolcreatedb "
    "FROM pg_roles WHERE rolname = current_user"
)
super_, createrole, bypassrls, createdb = cur.fetchone()
print(f"  rolsuper={super_} rolcreaterole={createrole} rolbypassrls={bypassrls} rolcreatedb={createdb}")
assert not (super_ or createrole or bypassrls or createdb), "应用角色仍有特权！"
print("  [OK] 无任何绕过 RLS 的特权")
c.close()

# 4) 双会话越权实测（直接 SQL，不经应用代码）
import uuid

A, B = "aaaaaaaa-0000-0000-0000-aaaaaaaaaaaa", "bbbbbbbb-0000-0000-0000-bbbbbbbbbbbb"
rid = f"rls-audit-{uuid.uuid4().hex[:12]}"

ca = psycopg2.connect(APP_DSN, connect_timeout=20)
ca.autocommit = False
ca.cursor().execute("SELECT set_config('app.user_id', %s, true)", (A,))
ca.cursor().execute(
    "INSERT INTO runs (run_id, project_input, user_id, status) VALUES (%s, %s, %s, 'running')",
    (rid, "RLS audit temp", A),
)
ca.commit()
ca.close()

section("4. 跨用户越权实测（B 会话尝试访问 A 的行）")
cb = psycopg2.connect(APP_DSN, connect_timeout=20)
cb.autocommit = False
curb = cb.cursor()
curb.execute("SELECT set_config('app.user_id', %s, true)", (B,))

curb.execute("SELECT count(*) FROM runs WHERE run_id = %s", (rid,))
seen = curb.fetchone()[0]
print(f"  B SELECT A 的行: 可见 {seen} 条（期望 0）-> {'OK' if seen == 0 else 'FAIL'}")

curb.execute("UPDATE runs SET status='failed' WHERE run_id = %s", (rid,))
updated = curb.rowcount
print(f"  B UPDATE A 的行: 影响 {updated} 行（期望 0）-> {'OK' if updated == 0 else 'FAIL'}")

curb.execute("DELETE FROM runs WHERE run_id = %s", (rid,))
deleted = curb.rowcount
print(f"  B DELETE A 的行: 影响 {deleted} 行（期望 0）-> {'OK' if deleted == 0 else 'FAIL'}")
cb.rollback()
cb.close()

# 未绑定/空身份（pooler 下新连接为 NULL 或 ''）也必须看不到
section("5. 空身份默认拒绝（含写入拦截）")
cn = psycopg2.connect(APP_DSN, connect_timeout=20)
cn.autocommit = False
cur = cn.cursor()
cur.execute("SELECT current_setting('app.user_id', true)")
unbound_val = cur.fetchone()[0]
print(f"  新连接未绑定时 app.user_id = {unbound_val!r}（NULL 或 '' 均须视为空身份）")
assert unbound_val is None or unbound_val == ""
cur.execute("SELECT count(*) FROM runs WHERE run_id = %s", (rid,))
seen_nobody = cur.fetchone()[0]
print(f"  空身份 SELECT A 的行: 可见 {seen_nobody} 条（期望 0）-> {'OK' if seen_nobody == 0 else 'FAIL'}")
cur.execute("SELECT count(*) FROM runs")
total_nobody = cur.fetchone()[0]
print(f"  空身份 SELECT 全表: 可见 {total_nobody} 条（期望 0）-> {'OK' if total_nobody == 0 else 'FAIL'}")

blocked_insert = False
try:
    cur.execute(
        "INSERT INTO runs (run_id, project_input, user_id, status) VALUES (%s,%s,'','running')",
        (f"empty-bind-{uuid.uuid4().hex[:8]}", "should be rejected"),
    )
except psycopg2.Error:
    blocked_insert = True
cn.rollback()
cn.close()
print(f"  空身份 INSERT user_id='' 行: {'OK 被策略拒绝' if blocked_insert else 'FAIL 居然写入成功'}")

# 6) A 自己能看到（防过度隔离）
ca = psycopg2.connect(APP_DSN, connect_timeout=20)
ca.autocommit = False
cura = ca.cursor()
cura.execute("SELECT set_config('app.user_id', %s, true)", (A,))
cura.execute("SELECT project_input FROM runs WHERE run_id = %s", (rid,))
own = cura.fetchone()
print(f"  A 看自己的行: {'OK' if own else 'FAIL'}（期望可见）")
cura.execute("DELETE FROM runs WHERE run_id = %s", (rid,))
ca.commit()
ca.close()
print("  审计假数据已清理")

assert seen == updated == deleted == seen_nobody == total_nobody == 0 and blocked_insert and own
print("\nRLS AUDIT: 全部通过")
