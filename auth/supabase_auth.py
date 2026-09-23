# -*- coding: utf-8 -*-
"""认证客户端 —— Supabase Auth 邮箱验证码回填注册 / 密码登录（方案 A）。

注册闭环（验证码回填版）：
  1) 用户填邮箱 + 密码 → 点击「注册并获取验证码」
  2) 后端调 supabase.auth.sign_up({email, password})
     Supabase 在开启 Confirm email + 邮件模板用 {{ .Token }} 后，
     创建用户、不发 Session、并向邮箱发送 6 位数字验证码
  3) 用户去邮箱查收验证码，回填到页面
  4) 后端调 supabase.auth.verify_otp({email, token, type="email"})
     验证通过 → 拿到登录态 Session + User → 进入主应用

登录闭环（已注册并完成邮箱确认的账号）：
  supabase.auth.sign_in_with_password({email, password}) → Session + User

前置条件（Supabase Dashboard 必须配置）：
  - Authentication → Sign in / Providers → Email → 开启 + Confirm email ON
  - Authentication → Email Templates → Confirm signup 模板用 {{ .Token }}
    （免费档默认模板不可改，必须配自定义 SMTP 才能编辑模板）
  - Authentication → SMTP Settings → 配置 Brevo/Resend 等 SMTP

不再保留本地 SQLite 回退：线上比赛作品只走一条 Supabase Auth 路径。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

# ── 关闭 httpx 自动读 Windows 系统代理 ──
# 背景：用户机器常装 Clash/V2Ray 等系统代理（注册表 ProxyServer=127.0.0.1:7890），
# supabase-py 内部 gotrue 创建 httpx.Client(verify=True, proxy=None, http2=True) 时
# 默认 trust_env=True，会调 urllib.request.getproxies() 读 Windows 注册表代理；
# 走代理转发 Supabase 的 HTTPS CONNECT 时 SSL 握手会超时（_ssl.c:1015 timed out）。
# 这里 monkey-patch getproxies 返回空 dict，让 httpx 全部直连，不影响国内 API（DeepSeek 等）。
import urllib.request as _urllib_request
_urllib_request.getproxies = lambda: {}
_urllib_request.getproxies_environment = lambda: {}
# 防止 Windows 平台回退到注册表代理
if hasattr(_urllib_request, "getproxies_registry"):
    _urllib_request.getproxies_registry = lambda: {}


@dataclass
class UserInfo:
    """统一用户信息（Supabase Auth 返回）。"""
    id: str                    # Supabase user UUID
    email: str
    created_at: str = ""
    metadata: dict = field(default_factory=dict)


class AuthClient:
    """Supabase Auth 客户端 —— 邮箱验证码回填注册 + 密码登录。

    必须配置 SUPABASE_URL + SUPABASE_ANON_KEY（或等价环境变量），
    未配置时所有 auth 操作直接报错，不静默回退到任何本地认证。
    """

    def __init__(self):
        self._client = None
        url = os.environ.get("SUPABASE_URL", "").strip()
        key = os.environ.get("SUPABASE_ANON_KEY", "").strip()
        if not url or not key:
            self._url = ""
            self._anon_key = ""
            return
        try:
            from supabase import create_client
            self._client = create_client(url, key)
            self._url = url
            self._anon_key = key
        except ImportError as e:
            raise RuntimeError(
                "supabase 包未安装，请运行: pip install supabase"
            ) from e

    # ── 配置检查 ──
    def is_configured(self) -> bool:
        return self._client is not None

    def is_supabase(self) -> bool:
        return self.is_configured()

    def _require_configured(self):
        if self._client is None:
            raise RuntimeError(
                "未配置 Supabase Auth。请在 .streamlit/secrets.toml 设置 "
                "SUPABASE_URL 与 SUPABASE_ANON_KEY 后重启应用。"
            )

    # ── 注册第一步：发送邮箱验证码 ──
    def signup_send_otp(self, email: str, password: str) -> None:
        """注册并发送邮箱验证码（不立即登录）。

        Supabase 在开启 Confirm email + 邮件模板用 {{ .Token }} 后，
        sign_up 会创建用户但不发 Session，并向邮箱发送 6 位数字验证码。

        成功：返回 None（UI 切换到「输入验证码」第二步）。
        失败：抛异常（如邮箱已注册、密码不符合策略、网络错误等）。
        """
        self._require_configured()
        email = (email or "").strip().lower()
        if not email or not password:
            raise ValueError("邮箱和密码不能为空")
        if len(password) < 6:
            raise ValueError("密码至少 6 位")
        try:
            res = self._client.auth.sign_up({
                "email": email,
                "password": password,
            })
        except Exception as e:
            msg = str(e)
            if "already" in msg.lower() or "registered" in msg.lower():
                raise ValueError("该邮箱已注册，请直接登录或换一个邮箱") from e
            if "rate limit" in msg.lower():
                raise RuntimeError("验证码发送过于频繁，请稍等 1 分钟再试") from e
            raise RuntimeError(f"注册失败：{msg[:200]}") from e
        user = getattr(res, "user", None) if res else None
        if user is None:
            raise RuntimeError("注册失败：Supabase 未返回用户信息，请检查邮箱格式或稍后重试")

    # ── 注册第二步：验证邮箱验证码 ──
    def verify_signup_otp(self, email: str, token: str) -> UserInfo:
        """回填邮箱验证码完成注册 → 返回登录态用户。

        调 supabase.auth.verify_otp({email, token, type="email"})，
        验证通过后 Supabase 返回 Session + User，用户完成邮箱确认并登录。
        """
        self._require_configured()
        email = (email or "").strip().lower()
        token = (token or "").strip()
        if not email or not token:
            raise ValueError("邮箱和验证码不能为空")
        try:
            res = self._client.auth.verify_otp({
                "email": email,
                "token": token,
                "type": "email",
            })
        except Exception as e:
            msg = str(e)
            if "invalid" in msg.lower() or "token" in msg.lower() or "otp" in msg.lower():
                raise ValueError("验证码错误或已过期，请重新获取") from e
            if "rate limit" in msg.lower():
                raise RuntimeError("验证过于频繁，请稍后再试") from e
            raise RuntimeError(f"验证失败：{msg[:200]}") from e
        user = getattr(res, "user", None) if res else None
        if not user:
            raise RuntimeError("验证失败：Supabase 未返回用户信息")
        return UserInfo(
            id=user.id,
            email=getattr(user, "email", "") or email,
            created_at=getattr(user, "created_at", "") or "",
        )

    # ── 密码登录 ──
    def sign_in(self, email: str, password: str) -> UserInfo:
        """邮箱 + 密码登录（已注册且完成邮箱确认的账号）。"""
        self._require_configured()
        email = (email or "").strip().lower()
        if not email or not password:
            raise ValueError("邮箱和密码不能为空")
        try:
            res = self._client.auth.sign_in_with_password({
                "email": email,
                "password": password,
            })
        except Exception as e:
            msg = str(e)
            if "invalid" in msg.lower() or "credentials" in msg.lower():
                raise ValueError("邮箱或密码错误") from e
            if "not confirmed" in msg.lower() or ("email" in msg.lower() and "confirm" in msg.lower()):
                raise ValueError("邮箱尚未验证，请先完成验证码注册") from e
            raise RuntimeError(f"登录失败：{msg[:200]}") from e
        user = getattr(res, "user", None) if res else None
        if not user:
            raise RuntimeError("登录失败：Supabase 未返回用户信息")
        return UserInfo(
            id=user.id,
            email=getattr(user, "email", "") or email,
            created_at=getattr(user, "created_at", "") or "",
        )

    # ── 退出登录 ──
    def sign_out(self):
        if self._client is None:
            return
        try:
            self._client.auth.sign_out()
        except Exception:
            pass

    # ── 获取当前 Session 用户（可选） ──
    def get_current_user(self) -> Optional[UserInfo]:
        if self._client is None:
            return None
        try:
            res = self._client.auth.get_user()
            user = getattr(res, "user", None) if res else None
            if not user:
                return None
            return UserInfo(
                id=user.id,
                email=getattr(user, "email", "") or "",
                created_at=getattr(user, "created_at", "") or "",
            )
        except Exception:
            return None


def get_auth_client() -> AuthClient:
    """工厂函数 —— 每次调用创建新客户端实例（短连接，无状态）。"""
    return AuthClient()
