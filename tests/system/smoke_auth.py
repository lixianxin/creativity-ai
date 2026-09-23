# -*- coding: utf-8 -*-
"""登录流程无头验证（Supabase 邮箱验证码回填注册版，方案 A）。

通过 monkey-patch `auth.get_auth_client` 注入 FakeAuthClient，
覆盖完整注册闭环：
  未登录 → 注册（发码）→ 回填验证码 → 进入主应用
  → 侧边栏身份 → 退出 → 再登录
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import auth as _auth_mod  # noqa: E402
from auth.supabase_auth import UserInfo  # noqa: E402


class _FakeUsers:
    def __init__(self):
        self._users = {}      # email -> password
        self._confirmed = set()

    def add(self, email, password):
        self._users[email] = password

    def confirm(self, email):
        self._confirmed.add(email)

    def verify(self, email, password):
        return self._users.get(email) == password


_FAKE_USERS = _FakeUsers()
_FAKE_OTP_CODE = "123456"  # FakeAuth 固定验证码


class FakeAuthClient:
    """模拟 Supabase Auth 的邮箱验证码回填注册流程。"""

    def is_configured(self) -> bool:
        return True

    def is_supabase(self) -> bool:
        return True

    def signup_send_otp(self, email: str, password: str) -> None:
        """注册第一步：发验证码（不立即登录）。"""
        email = (email or "").strip().lower()
        if not email or not password:
            raise ValueError("邮箱和密码不能为空")
        if len(password) < 6:
            raise ValueError("密码至少 6 位")
        if email in _FAKE_USERS._users:
            raise ValueError("该邮箱已注册，请直接登录或换一个邮箱")
        _FAKE_USERS.add(email, password)
        # 模拟 Supabase 发送验证码邮件（验证码固定 123456）

    def verify_signup_otp(self, email: str, token: str) -> UserInfo:
        """注册第二步：回填验证码完成注册 → 返回登录态用户。"""
        email = (email or "").strip().lower()
        token = (token or "").strip()
        if token != _FAKE_OTP_CODE:
            raise ValueError("验证码错误或已过期，请重新获取")
        if email not in _FAKE_USERS._users:
            raise ValueError("该邮箱未注册，请先注册")
        _FAKE_USERS.confirm(email)
        return UserInfo(id=f"uuid-{email}", email=email, created_at="2026-09-22 10:00:00")

    def sign_in(self, email: str, password: str) -> UserInfo:
        email = (email or "").strip().lower()
        if not _FAKE_USERS.verify(email, password):
            raise ValueError("邮箱或密码错误")
        if email not in _FAKE_USERS._confirmed:
            raise ValueError("邮箱尚未验证，请先完成验证码注册")
        return UserInfo(id=f"uuid-{email}", email=email, created_at="2026-09-22 10:00:00")

    def sign_out(self):
        pass

    def get_current_user(self):
        return None


_auth_mod.get_auth_client = lambda: FakeAuthClient()

from streamlit.testing.v1 import AppTest  # noqa: E402

APP_PATH = str(ROOT / "frontend" / "app.py")
LOGIN_BTN = "FormSubmitter:cx_login_form-登录"
SIGNUP_BTN = "FormSubmitter:cx_signup_form-注册并获取验证码"
OTP_BTN = "FormSubmitter:cx_signup_otp_form-验证并注册"

# ── 1) 首次打开：应显示认证页（标题 + Tab + 登录表单 + 注册第一步表单） ──
at = AppTest.from_file(APP_PATH, default_timeout=30)
at.run()

markdown_text = "\n".join(m.value for m in at.markdown)
assert "创想∞ AI创业委员会" in markdown_text, "标题未渲染"
btn_keys = [b.key for b in at.button]
assert LOGIN_BTN in btn_keys, f"缺少登录按钮: {btn_keys}"
assert SIGNUP_BTN in btn_keys, f"缺少注册按钮: {btn_keys}"
input_keys = {t.key for t in at.text_input}
assert input_keys == {"login_email", "login_pwd", "signup_email", "signup_pwd", "signup_pwd2"}, \
    f"输入框集合不对: {input_keys}"
assert not at.exception, f"首屏异常: {[e.message for e in at.exception]}"
print("[1/6] OK 未登录显示认证页：标题 + 登录表单 + 注册第一步表单")

# ── 2) 注册第一步：填邮箱+密码 → 点「注册并获取验证码」→ 切到第二步 ──
at.get_by_key("signup_email").set_value("smoke@test.com").run()
at.get_by_key("signup_pwd").set_value("smoke123").run()
at.get_by_key("signup_pwd2").set_value("smoke123").run()
at.get_by_key(SIGNUP_BTN).click().run()

assert not at.exception, f"注册第一步异常: {[e.message for e in at.exception]}"
btn_keys = [b.key for b in at.button]
assert SIGNUP_BTN not in btn_keys, f"注册按钮仍在（应已切到第二步）: {btn_keys}"
assert OTP_BTN in btn_keys, f"缺少验证码确认按钮: {btn_keys}"
md_text = "\n".join(m.value for m in at.markdown)
assert "smoke@test.com" in md_text, "未显示目标邮箱"
assert "验证码已发送" in md_text or "验证你的邮箱" in md_text, "未显示验证码发送提示"
print("[2/6] OK 注册第一步成功，切换到「输入邮箱验证码」第二步")

# ── 3) 回填验证码 → 点「验证并注册」→ 进入主应用 ──
at.get_by_key("signup_otp").set_value(_FAKE_OTP_CODE).run()
at.get_by_key(OTP_BTN).click().run()

assert not at.exception, f"验证码确认异常: {[e.message for e in at.exception]}"
assert len(at.radio) >= 1, "验证后未进入主应用"
nav_labels = at.radio[0].options
assert "＋ 新建审议" in nav_labels, f"导航项不对: {nav_labels}"
print("[3/6] OK 验证码回填成功，进入主应用，导航项:", nav_labels)

# ── 4) 侧边栏应显示当前用户邮箱与退出按钮 ──
sidebar_text = "\n".join(m.value for m in at.sidebar.markdown)
assert "smoke@test.com" in sidebar_text, "侧边栏未显示用户邮箱"
assert any("退出登录" in b.label for b in at.sidebar.button), "未找到退出按钮"
print("[4/6] OK 侧边栏显示用户邮箱 + 退出按钮")

# ── 5) 退出登录：应回到认证页（注册态已清空） ──
logout_btn = [b for b in at.sidebar.button if "退出登录" in b.label][0]
logout_btn.click().run()
btn_keys2 = [b.key for b in at.button]
assert LOGIN_BTN in btn_keys2, "退出后未回到认证页"
assert SIGNUP_BTN in btn_keys2, "退出后未恢复注册表单"
assert OTP_BTN not in btn_keys2, "退出后仍停留在验证码第二步"
assert len(at.radio) == 0, "退出后仍显示业务导航"
print("[5/6] OK 退出登录，回到认证页（注册态已清空）")

# ── 6) 用刚注册的账号走登录表单 ──
at2 = AppTest.from_file(APP_PATH, default_timeout=30)
at2.run()
at2.get_by_key("login_email").set_value("smoke@test.com").run()
at2.get_by_key("login_pwd").set_value("smoke123").run()
at2.get_by_key(LOGIN_BTN).click().run()
assert not at2.exception, f"再次登录后异常: {[e.message for e in at2.exception]}"
assert len(at2.radio) >= 1, "再次登录后未进入主应用"
print("[6/6] OK 用已注册账号登录成功，进入主应用")

print("\n全部断言通过：注册发码 → 回填验证码 → 进入主应用 → 退出 → 再登录")
