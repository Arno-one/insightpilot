from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Any

from app.core.config import settings


def smtp_is_configured() -> bool:
    """中文注释：只有 SMTP 关键配置齐全时才尝试真实发信，避免把异常噪音带进业务链路。"""

    return all(
        [
            settings.smtp_host.strip(),
            settings.sender_email.strip(),
            settings.smtp_auth_code.strip(),
        ]
    )


def _should_use_ssl() -> bool:
    if settings.smtp_use_ssl is not None:
        return settings.smtp_use_ssl
    return settings.smtp_port == 465


def send_email_message(*, recipient_email: str, subject: str, content: str) -> dict[str, Any]:
    """中文注释：统一封装 SMTP 发送，后续切换到真实 Mail MCP 时只需要替换这一层。"""

    if not smtp_is_configured():
        raise RuntimeError("SMTP 配置不完整，无法发送邮件")
    if not recipient_email.strip():
        raise RuntimeError("收件人邮箱为空，无法发送邮件")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{settings.smtp_sender_name} <{settings.sender_email}>"
    message["To"] = recipient_email
    message.set_content(content)

    timeout = max(settings.smtp_timeout_seconds, 1)
    if _should_use_ssl():
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=timeout) as client:
            client.login(settings.sender_email, settings.smtp_auth_code)
            client.send_message(message)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=timeout) as client:
            client.ehlo()
            if settings.smtp_use_tls:
                client.starttls()
                client.ehlo()
            client.login(settings.sender_email, settings.smtp_auth_code)
            client.send_message(message)

    return {
        "provider": "smtp",
        "sender_email": settings.sender_email,
        "recipient_email": recipient_email,
        "subject": subject,
    }


def send_task_assignment_email(
    *,
    recipient_email: str,
    recipient_name: str | None,
    task: dict[str, Any],
    approval: dict[str, Any],
) -> dict[str, Any]:
    """中文注释：先把任务分配邮件做成模板函数，后面扩展更多通知类型时可复用。"""

    subject = f"【InsightPilot】新任务待处理：{task['title']}"
    salutation = recipient_name or "同事"
    content = (
        f"{salutation}，你好：\n\n"
        f"InsightPilot 已为你生成一条新的跟进任务。\n"
        f"任务标题：{task['title']}\n"
        f"客户 ID：{approval['customer_id']}\n"
        f"优先级：{task.get('priority') or 'medium'}\n"
        f"截止时间：{task.get('due_at') or '尽快处理'}\n\n"
        f"任务说明：{task.get('description') or '请尽快进入系统查看任务详情并完成跟进。'}\n\n"
        f"请及时处理，避免客户跟进中断。\n"
        f"本邮件由 InsightPilot 自动发送。"
    )
    result = send_email_message(recipient_email=recipient_email, subject=subject, content=content)
    result["recipient_name"] = recipient_name
    return result
