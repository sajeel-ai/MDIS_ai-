"""Environment-configured auth email delivery. Secrets and links are never logged."""

import asyncio
import smtplib
from email.message import EmailMessage
from typing import Protocol
from urllib.parse import urlencode, urlsplit

import httpx

from app.config import settings
from app.services.email_templates import EmailTemplate, render_email


class EmailProvider(Protocol):
    async def send(self, recipient: str, subject: str, body: str, html_body: str | None = None) -> None: ...


class SMTPEmailProvider:
    async def send(self, recipient: str, subject: str, body: str, html_body: str | None = None) -> None:
        message = EmailMessage()
        message["From"] = settings.email_from
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(body)
        if html_body:
            message.add_alternative(html_body, subtype="html")

        def deliver() -> None:
            with smtplib.SMTP(
                settings.smtp_host,
                settings.smtp_port,
                timeout=settings.email_send_timeout_seconds,
            ) as client:
                if settings.smtp_starttls:
                    client.starttls()
                if settings.smtp_username:
                    client.login(settings.smtp_username, settings.smtp_password)
                client.send_message(message)

        await asyncio.to_thread(deliver)


class ResendEmailProvider:
    async def send(self, recipient: str, subject: str, body: str, html_body: str | None = None) -> None:
        payload: dict[str, object] = {
            "from": settings.email_from,
            "to": [recipient],
            "subject": subject,
            "text": body,
        }
        if html_body:
            payload["html"] = html_body
        async with httpx.AsyncClient(timeout=settings.email_send_timeout_seconds) as client:
            response = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                json=payload,
            )
            response.raise_for_status()


class SendGridEmailProvider:
    async def send(self, recipient: str, subject: str, body: str, html_body: str | None = None) -> None:
        content = [{"type": "text/plain", "value": body}]
        if html_body:
            content.append({"type": "text/html", "value": html_body})
        async with httpx.AsyncClient(timeout=settings.email_send_timeout_seconds) as client:
            response = await client.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={"Authorization": f"Bearer {settings.sendgrid_api_key}"},
                json={
                    "personalizations": [{"to": [{"email": recipient}]}],
                    "from": {"email": settings.email_from},
                    "subject": subject,
                    "content": content,
                },
            )
            response.raise_for_status()


def configured_email_provider() -> EmailProvider | None:
    if not settings.email_from:
        return None
    if settings.email_provider == "smtp" and settings.smtp_host:
        return SMTPEmailProvider()
    if settings.email_provider == "resend" and settings.resend_api_key:
        return ResendEmailProvider()
    if settings.email_provider == "sendgrid" and settings.sendgrid_api_key:
        return SendGridEmailProvider()
    return None


def email_delivery_available() -> bool:
    if configured_email_provider() is None:
        return False
    base = settings.public_app_url.strip().rstrip("/")
    parsed = urlsplit(base)
    return (
        parsed.scheme in {"https", "http"}
        and bool(parsed.netloc)
        and parsed.username is None
        and parsed.password is None
    )


def action_link(purpose: str, token: str) -> str | None:
    if not settings.public_app_url:
        return None
    base = settings.public_app_url.rstrip("/")
    parsed = urlsplit(base)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc or parsed.username or parsed.password:
        return None
    route_by_purpose = {
        "password-reset": "/reset-password",
        "invite-accept": "/accept-invitation",
        "verify-email": "/verify-email",
    }
    route = route_by_purpose.get(purpose)
    return f"{base}{route}?{urlencode({'token': token})}" if route else None


async def send_templated_email(
    recipient: str,
    template: EmailTemplate,
    *,
    display_name: str = "",
    action_url: str | None = None,
    verification_code: str | None = None,
) -> bool:
    provider = configured_email_provider()
    if provider is None:
        return False
    rendered = render_email(
        template,
        display_name=display_name,
        action_url=action_url,
        verification_code=verification_code,
    )
    for attempt in range(settings.email_retry_attempts):
        try:
            await asyncio.wait_for(
                provider.send(recipient, rendered.subject, rendered.text, rendered.html),
                timeout=settings.email_send_timeout_seconds,
            )
            return True
        except Exception:
            if attempt + 1 >= settings.email_retry_attempts:
                raise
            delay = min(settings.email_retry_backoff_seconds * (2**attempt), 5.0)
            if delay:
                await asyncio.sleep(delay)
    return False


async def send_action_link(recipient: str, purpose: str, token: str) -> bool:
    link = action_link(purpose, token)
    if not link:
        return False
    template_by_purpose = {
        "password-reset": EmailTemplate.PASSWORD_RESET,
        "invite-accept": EmailTemplate.INVITATION,
        "verify-email": EmailTemplate.VERIFY_EMAIL,
    }
    template = template_by_purpose.get(purpose)
    if template is None:
        return False
    return await send_templated_email(recipient, template, action_url=link)


async def send_password_changed_notice(recipient: str, display_name: str = "") -> bool:
    return await send_templated_email(recipient, EmailTemplate.SECURITY_ALERT, display_name=display_name)


async def send_account_notice(recipient: str, template: EmailTemplate, display_name: str = "") -> bool:
    if template not in {EmailTemplate.ACCOUNT_APPROVED, EmailTemplate.ACCOUNT_REJECTED, EmailTemplate.ACCOUNT_EXISTS}:
        raise ValueError("Unsupported account notice template")
    return await send_templated_email(recipient, template, display_name=display_name)


async def send_verification_code(recipient: str, purpose: str, code: str) -> bool:
    template_by_purpose = {
        "verify_email": EmailTemplate.VERIFY_EMAIL,
        "reset_password": EmailTemplate.PASSWORD_RESET,
        "mfa_fallback": EmailTemplate.MFA_FALLBACK,
    }
    template = template_by_purpose.get(purpose)
    if template is None:
        return False
    return await send_templated_email(recipient, template, verification_code=code)
