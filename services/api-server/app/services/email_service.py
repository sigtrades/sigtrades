"""邮件发送：优先 Resend，回退 SMTP，未配置则 dev 日志。"""

from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

# 邮件主色：与 web brand 对齐（绿色）
_BRAND = "#10b981"
_BRAND_DARK = "#059669"
_TEXT = "#0f172a"
_MUTED = "#64748b"
_BG = "#f8fafc"


def _is_en(lang: Optional[str]) -> bool:
    return (lang or "zh").lower().startswith("en")


def _is_configured() -> bool:
    if settings.RESEND_API_KEY and settings.RESEND_FROM_EMAIL:
        return True
    return bool(settings.SMTP_HOST)


def send_email(
    to: str,
    subject: str,
    html: str,
    text_body: Optional[str] = None,
    *,
    from_email: Optional[str] = None,
) -> bool:
    if settings.RESEND_API_KEY and (from_email or settings.RESEND_FROM_EMAIL):
        return _send_via_resend(to, subject, html, text_body, from_email=from_email)
    if settings.SMTP_HOST:
        return _send_via_smtp(to, subject, html)
    logger.info("[email:dev] to=%s subject=%s\n%s", to, subject, html)
    return True


def _send_via_resend(
    to: str,
    subject: str,
    html: str,
    text_body: Optional[str] = None,
    *,
    from_email: Optional[str] = None,
) -> bool:
    try:
        import resend

        resend.api_key = settings.RESEND_API_KEY
        addr = (from_email or settings.RESEND_FROM_EMAIL or "").strip()
        if not addr:
            logger.error("Resend send failed: missing from email")
            return False
        from_line = f"{settings.RESEND_FROM_NAME} <{addr}>" if settings.RESEND_FROM_NAME else addr
        params: resend.Emails.SendParams = {
            "from": from_line,
            "to": [to],
            "subject": subject,
            "html": html,
        }
        if text_body:
            params["text"] = text_body
        result = resend.Emails.send(params)
        email_id = (result or {}).get("id") if isinstance(result, dict) else None
        logger.info("Resend email sent to=%s subject=%s id=%s", to, subject, email_id)
        return True
    except Exception as e:  # noqa: BLE001
        logger.error("Resend send failed to=%s: %s", to, e)
        return False


def _send_via_smtp(to: str, subject: str, html: str) -> bool:
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_FROM
        msg["To"] = to
        msg.attach(MIMEText(html, "html", "utf-8"))
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
            if settings.SMTP_USE_TLS:
                server.starttls()
            if settings.SMTP_USER:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_FROM, [to], msg.as_string())
        return True
    except Exception as e:  # noqa: BLE001
        logger.error("SMTP send_email failed: %s", e)
        return False


def _simple_email_html(
    *,
    en: bool,
    title: str,
    body: str,
    cta_text: str,
    cta_url: str,
    footnote: str,
    summary_lines: Optional[list[str]] = None,
    show_url: bool = True,
) -> str:
    """简洁单列模板：品牌名 + 标题 + 正文 + 可选摘要列表 + 按钮 + 脚注。"""
    lang = "en" if en else "zh-CN"
    lines = [str(x).strip() for x in (summary_lines or []) if str(x).strip()]
    lines_html = ""
    if lines:
        items = "".join(
            f'<li style="margin:0 0 6px;font-size:14px;color:#334155;">{line}</li>'
            for line in lines
        )
        lines_html = f'<ul style="margin:16px 0 0;padding-left:18px;">{items}</ul>'
    cta_html = ""
    if cta_text and cta_url:
        cta_html = f"""
    <p style="margin:24px 0 0;">
      <a href="{cta_url}" style="display:inline-block;background:{_BRAND};color:#ffffff;padding:11px 20px;border-radius:8px;text-decoration:none;font-size:14px;font-weight:600;">{cta_text}</a>
    </p>"""
        if show_url:
            cta_html += f"""
    <p style="margin:16px 0 0;font-size:12px;line-height:1.5;word-break:break-all;">
      <a href="{cta_url}" style="color:{_BRAND_DARK};text-decoration:underline;">{cta_url}</a>
    </p>"""
    foot = (
        f'<p style="margin:20px 0 0;font-size:12px;line-height:1.5;color:{_MUTED};">{footnote}</p>'
        if footnote
        else ""
    )
    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:32px 16px;background:{_BG};font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:{_TEXT};">
  <div style="max-width:480px;margin:0 auto;background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:28px 24px;">
    <p style="margin:0;font-size:15px;font-weight:700;letter-spacing:-0.02em;color:{_BRAND_DARK};">sigtrades</p>
    <h1 style="margin:20px 0 0;font-size:20px;font-weight:700;line-height:1.3;">{title}</h1>
    <p style="margin:12px 0 0;font-size:14px;line-height:1.65;color:#475569;">{body}</p>
    {lines_html}
    {cta_html}
    {foot}
  </div>
</body>
</html>"""


def send_notify_email(
    to_email: str,
    *,
    subject: str,
    title: str,
    body: str,
    summary_lines: Optional[list[str]] = None,
    lang: Optional[str] = None,
    cta_text: Optional[str] = None,
    footnote: str = "",
) -> bool:
    """通知类邮件统一模板（不再附带原始 JSON）。"""
    en = _is_en(lang)
    dashboard = f"{settings.FRONTEND_URL.rstrip('/')}/app"
    if en:
        cta = cta_text or "Open dashboard"
        text_lines = [title, "", body, ""] + list(summary_lines or []) + ["", f"Dashboard: {dashboard}"]
    else:
        cta = cta_text or "打开控制台"
        text_lines = [title, "", body, ""] + list(summary_lines or []) + ["", f"控制台：{dashboard}"]
    html = _simple_email_html(
        en=en,
        title=title,
        body=body,
        cta_text=cta,
        cta_url=dashboard,
        footnote=footnote,
        summary_lines=summary_lines,
        show_url=False,
    )
    return send_email(to_email, subject, html, "\n".join(text_lines))


def send_verification_email(to_email: str, token: str, lang: Optional[str] = None) -> bool:
    verify_url = f"{settings.FRONTEND_URL}/verify-email?token={token}"
    en = _is_en(lang)
    if en:
        subject = "Verify your email — sigtrades"
        html = _simple_email_html(
            en=True,
            title="Verify your email",
            body="Thanks for signing up. Click the button below to activate your account.",
            cta_text="Verify email",
            cta_url=verify_url,
            footnote="If you did not sign up, ignore this email. Link expires in 24 hours.",
        )
        text = f"Verify your email: {verify_url}\n\nLink expires in 24 hours."
    else:
        subject = "请验证您的邮箱 — sigtrades"
        html = _simple_email_html(
            en=False,
            title="欢迎加入 sigtrades",
            body="感谢注册。请点击下方按钮验证邮箱以激活账号。",
            cta_text="验证邮箱",
            cta_url=verify_url,
            footnote="若您未注册账号，请忽略此邮件。链接 24 小时内有效。",
        )
        text = f"请验证邮箱：{verify_url}\n\n链接 24 小时内有效。"
    return send_email(to_email, subject, html, text)


def send_password_reset_email(to_email: str, token: str, lang: Optional[str] = None) -> bool:
    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    en = _is_en(lang)
    if en:
        subject = "Reset your password — sigtrades"
        html = _simple_email_html(
            en=True,
            title="Reset your password",
            body="We received a password reset request for your account.",
            cta_text="Reset password",
            cta_url=reset_url,
            footnote="If you did not request this, ignore this email. Link expires in 1 hour.",
        )
        text = f"Reset your password: {reset_url}\n\nLink expires in 1 hour."
    else:
        subject = "重置密码 — sigtrades"
        html = _simple_email_html(
            en=False,
            title="重置密码",
            body="我们收到了您账号的密码重置请求。",
            cta_text="重置密码",
            cta_url=reset_url,
            footnote="若您未发起此请求，请忽略此邮件。链接 1 小时内有效。",
        )
        text = f"重置密码：{reset_url}\n\n链接 1 小时内有效。"
    return send_email(to_email, subject, html, text)


def send_pending_confirm_email(
    to_email: str,
    *,
    confirm_url: str,
    reject_url: str,
    summary_lines: list[str],
    lang: Optional[str] = None,
) -> bool:
    """手动确认交易：邮件内含确认/取消按钮（点开后仍需落地页再点一次）。"""
    en = _is_en(lang)
    lines_html = "".join(
        f'<li style="margin:0 0 6px;font-size:14px;color:#334155;">{line}</li>'
        for line in summary_lines
        if line
    )
    if en:
        subject = "Confirm trade — sigtrades"
        title = "Manual confirmation required"
        body = "A signal is waiting for your confirmation. Open a button below, then confirm again on the page (prevents accidental clicks)."
        confirm_text = "Confirm trade"
        reject_text = "Cancel"
        footnote = "Links expire in 5 minutes. Confirming will place the order if your Agent/broker is ready."
        text = (
            f"Confirm trade:\n{confirm_url}\n\nCancel:\n{reject_url}\n\n"
            + "\n".join(summary_lines)
            + "\n\nLinks expire in 5 minutes."
        )
    else:
        subject = "待确认交易 — sigtrades"
        title = "需要您确认后才会下单"
        body = "收到一条需手动确认的信号。请先点下方按钮打开页面，再在页面上点一次确认（防止邮件预取误操作）。"
        confirm_text = "确认执行"
        reject_text = "取消"
        footnote = "链接 5 分钟内有效。确认后将按原流水线下单（网关类券商需 Agent 在线）。"
        text = (
            f"确认执行：\n{confirm_url}\n\n取消：\n{reject_url}\n\n"
            + "\n".join(summary_lines)
            + "\n\n链接 5 分钟内有效。"
        )

    lang_attr = "en" if en else "zh-CN"
    html = f"""<!DOCTYPE html>
<html lang="{lang_attr}">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:32px 16px;background:{_BG};font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:{_TEXT};">
  <div style="max-width:480px;margin:0 auto;background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:28px 24px;">
    <p style="margin:0;font-size:15px;font-weight:700;letter-spacing:-0.02em;color:{_BRAND_DARK};">sigtrades</p>
    <h1 style="margin:20px 0 0;font-size:20px;font-weight:700;line-height:1.3;">{title}</h1>
    <p style="margin:12px 0 0;font-size:14px;line-height:1.65;color:#475569;">{body}</p>
    <ul style="margin:16px 0 0;padding-left:18px;">{lines_html}</ul>
    <p style="margin:24px 0 0;">
      <a href="{confirm_url}" style="display:inline-block;background:{_BRAND};color:#ffffff;padding:11px 20px;border-radius:8px;text-decoration:none;font-size:14px;font-weight:600;margin-right:10px;">{confirm_text}</a>
      <a href="{reject_url}" style="display:inline-block;background:#f1f5f9;color:#334155;padding:11px 20px;border-radius:8px;text-decoration:none;font-size:14px;font-weight:600;">{reject_text}</a>
    </p>
    <p style="margin:20px 0 0;font-size:12px;line-height:1.5;color:{_MUTED};">{footnote}</p>
  </div>
</body>
</html>"""
    return send_email(to_email, subject, html, text)


def send_subscription_email(to_email: str, plan_name: str, lang: Optional[str] = None) -> bool:
    url = f"{settings.FRONTEND_URL}/app"
    en = _is_en(lang)
    if en:
        subject = f"Subscription active — {plan_name}"
        html = _simple_email_html(
            en=True,
            title=f"{plan_name} is active",
            body=f"Thanks for subscribing to {plan_name}. You can manage billing in the dashboard.",
            cta_text="Open dashboard",
            cta_url=url,
            footnote="",
        )
        text = f"Your {plan_name} plan is active. Open: {url}"
    else:
        subject = f"订阅已生效 — {plan_name}"
        html = _simple_email_html(
            en=False,
            title=f"{plan_name} 已生效",
            body=f"感谢订阅 {plan_name}。可在控制台管理订阅与信号配置。",
            cta_text="打开控制台",
            cta_url=url,
            footnote="",
        )
        text = f"您的 {plan_name} 订阅已生效。打开：{url}"
    return send_email(to_email, subject, html, text)


def send_inbound_reply(
    *,
    to_email: str,
    from_email: str,
    subject: str,
    text_body: str,
    html_body: Optional[str] = None,
    in_reply_to: Optional[str] = None,
    reply_to: Optional[str] = None,
) -> bool:
    if not settings.RESEND_API_KEY:
        logger.info("[email:dev] inbound reply to=%s subject=%s\n%s", to_email, subject, text_body)
        return True
    try:
        import resend

        resend.api_key = settings.RESEND_API_KEY
        from_line = f"{settings.RESEND_FROM_NAME} <{from_email}>" if settings.RESEND_FROM_NAME else from_email
        params: resend.Emails.SendParams = {
            "from": from_line,
            "to": [to_email],
            "subject": subject,
            "text": text_body,
        }
        if html_body:
            params["html"] = html_body
        if in_reply_to:
            params["headers"] = {"In-Reply-To": in_reply_to, "References": in_reply_to}
        if reply_to:
            params["reply_to"] = reply_to
        resend.Emails.send(params)
        return True
    except Exception as e:  # noqa: BLE001
        logger.error("inbound reply failed: %s", e)
        return False
