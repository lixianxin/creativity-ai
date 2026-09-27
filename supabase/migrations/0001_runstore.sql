-- RunStore PG Schema：与 core/run_store.py 的 SQLite 版字段一一对应。
-- 应用启动时（SUPABASE_DB_URL 已配置）自动执行本文件，幂等可重复；
-- 同时作为 Supabase 迁移留档（唯一 DDL 源，勿在别处重复维护建表语句）。

-- ── runs：一次完整的 12 棒委员会审查 ──
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    user_id TEXT DEFAULT '',
    project_id TEXT DEFAULT '',
    status TEXT NOT NULL,
    current_stage TEXT DEFAULT '',
    project_input TEXT DEFAULT '',
    report_dir TEXT DEFAULT '',
    error TEXT DEFAULT '',
    pause_reason TEXT DEFAULT '',
    metadata_json JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_user ON runs(user_id);

-- ── agent_runs：Run 内单个 Agent 的执行记录（checkpoint）──
-- user_id 反规范化落列：与 runs 用同一套简单策略即可完成隔离，
-- 免去 EXISTS 子查询策略（更简单、更快、行为一致）。
CREATE TABLE IF NOT EXISTS agent_runs (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL,
    user_id TEXT NOT NULL DEFAULT '',
    agent_name TEXT NOT NULL,
    stage_seq TEXT DEFAULT '',
    stage_key TEXT DEFAULT '',
    label TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'queued',
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    retry_count INTEGER DEFAULT 0,
    conclusion TEXT DEFAULT '',
    output_path TEXT DEFAULT '',
    error TEXT DEFAULT '',
    validation_json JSONB DEFAULT '{}',
    metadata_json JSONB DEFAULT '{}',
    UNIQUE (run_id, agent_name)
);
CREATE INDEX IF NOT EXISTS idx_agent_runs_run ON agent_runs(run_id, stage_seq);

-- ── 行级安全：数据库强制 user_id 隔离 ──
-- 会话变量 app.user_id 由 RunStore 每次建连时以 set_config(..., true) 事务级绑定；
-- 未绑定时 current_setting 返回 NULL，所有行不可见（默认拒绝）。
-- FORCE 使表 owner 也受策略约束，应用层漏写 WHERE 无法越权。
-- (SELECT ...) 包裹让 current_setting 成为 initplan，避免逐行求值。
-- NULLIF 闸：空字符串身份（如忘记绑定/连接池默认值）一律拒绝读写，
-- 防止 user_id='' 的行成为"无主共享行"。
ALTER TABLE runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE runs FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS runs_user_isolation ON runs;
CREATE POLICY runs_user_isolation ON runs
    FOR ALL
    USING (
        NULLIF((SELECT current_setting('app.user_id', true)), '') IS NOT NULL
        AND user_id = (SELECT current_setting('app.user_id', true))
    )
    WITH CHECK (
        NULLIF((SELECT current_setting('app.user_id', true)), '') IS NOT NULL
        AND user_id = (SELECT current_setting('app.user_id', true))
    );

ALTER TABLE agent_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_runs FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS agent_runs_user_isolation ON agent_runs;
CREATE POLICY agent_runs_user_isolation ON agent_runs
    FOR ALL
    USING (
        NULLIF((SELECT current_setting('app.user_id', true)), '') IS NOT NULL
        AND user_id = (SELECT current_setting('app.user_id', true))
    )
    WITH CHECK (
        NULLIF((SELECT current_setting('app.user_id', true)), '') IS NOT NULL
        AND user_id = (SELECT current_setting('app.user_id', true))
    );

-- ── 应用专用角色（最小权限）──
-- 关键：应用绝不能用 postgres 超级用户连接——superuser 无条件绕过 RLS，
-- 连 FORCE 也拦不住。runstore_app 只是普通登录角色（非 owner、无 BYPASSRLS），
-- RLS 对其强制执行。
-- 角色含密码的 CREATE/ALTER ROLE 属一次性开通，不随本文件提交；
-- 以 postgres 身份执行（见 README「数据库开通」）：
--   CREATE ROLE runstore_app LOGIN PASSWORD '你自己设定的密码';
-- 角色已存在后，下面的授权幂等执行：
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'runstore_app') THEN
        GRANT USAGE ON SCHEMA public TO runstore_app;
        GRANT SELECT, INSERT, UPDATE, DELETE ON runs, agent_runs TO runstore_app;
        GRANT USAGE, SELECT ON SEQUENCE agent_runs_id_seq TO runstore_app;
    END IF;
END $$;
