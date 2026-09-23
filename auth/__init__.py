# -*- coding: utf-8 -*-
"""认证模块 —— Supabase Auth 邮箱验证码回填注册 / 密码登录（方案 A）。

架构原则（与改写.md 一致）：
- 认证是独立的一层，不碰 Agent / Registry / DAG / Orchestrator / Validator / Repair / LLM；
- 只走 Supabase Auth 一条路径，不再保留本地 SQLite 回退（线上比赛作品认证逻辑必须唯一）；
- 注册闭环：sign_up 发送验证码邮件 → 用户回填验证码 → verify_otp(type=email) → 登录主系统；
- 登录闭环：sign_in_with_password（已注册并完成邮箱确认的账号）；
- user_id 注入 RunStore，最近项目按 user_id 过滤。

前置条件（Supabase Dashboard 必须配置）：
- Authentication → Sign in / Providers → Email → 开启 + Confirm email ON
- Authentication → SMTP Settings → 配置自定义 SMTP（Brevo/Resend 等）
- Authentication → Email Templates → Confirm signup 模板用 {{ .Token }}

对外暴露：
- AuthClient     认证客户端（仅 Supabase Auth）
- get_auth_client()  工厂函数（读 SUPABASE_URL/SUPABASE_ANON_KEY 环境变量）
- UserInfo       统一用户信息数据类
"""
from auth.supabase_auth import AuthClient, get_auth_client, UserInfo

__all__ = ["AuthClient", "get_auth_client", "UserInfo"]
