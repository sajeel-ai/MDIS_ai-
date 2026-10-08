"""Allowlisted transactional email templates. Template variables are escaped."""

from dataclasses import dataclass
from enum import StrEnum
from html import escape
import re
from urllib.parse import urlsplit


class EmailTemplate(StrEnum):
    VERIFY_EMAIL = "verify_email"
    PASSWORD_RESET = "password_reset"
    ACCOUNT_APPROVED = "account_approved"
    ACCOUNT_REJECTED = "account_rejected"
    INVITATION = "invitation"
    SECURITY_ALERT = "security_alert"
    MFA_FALLBACK = "mfa_fallback"
    ACCOUNT_EXISTS = "account_exists"


@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    text: str
    html: str


_COPY = {
    EmailTemplate.VERIFY_EMAIL: ("Verify your Cognate AI email", "Verify your email address"),
    EmailTemplate.PASSWORD_RESET: ("Reset your Cognate AI password", "Reset your password"),
    EmailTemplate.ACCOUNT_APPROVED: ("Your Cognate AI account is approved", "Your account is approved"),
    EmailTemplate.ACCOUNT_REJECTED: ("Cognate AI account request update", "Account request update"),
    EmailTemplate.INVITATION: ("You are invited to Cognate AI", "Accept your invitation"),
    EmailTemplate.SECURITY_ALERT: ("Cognate AI security notice", "Your password was changed"),
    EmailTemplate.MFA_FALLBACK: ("Cognate AI sign-in code", "Your sign-in code"),
    EmailTemplate.ACCOUNT_EXISTS: ("Cognate AI account notice", "An account already exists"),
}


def render_email(
    template: EmailTemplate,
    *,
    display_name: str = "",
    action_url: str | None = None,
    verification_code: str | None = None,
) -> RenderedEmail:
    """Render a small, branded text and HTML message without remote assets."""
    if action_url:
        parsed = urlsplit(action_url)
        if parsed.scheme not in {"https", "http"} or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError("Email action URL must be an absolute HTTP(S) URL")
    if verification_code is not None and not re.fullmatch(r"\d{6}", verification_code):
        raise ValueError("Verification codes must contain six digits")

    subject, heading = _COPY[template]
    plain_name = display_name.strip()
    safe_name = escape(plain_name)
    text_greeting = f"Hello {plain_name}," if plain_name else "Hello,"
    html_greeting = f"Hello {safe_name}," if safe_name else "Hello,"
    if template is EmailTemplate.PASSWORD_RESET:
        explanation = "We received a request to reset the password for your account."
    elif template is EmailTemplate.INVITATION:
        explanation = "An administrator invited you to create an account."
    elif template is EmailTemplate.VERIFY_EMAIL:
        explanation = "Confirm this email address to continue setting up your account."
    elif template is EmailTemplate.ACCOUNT_APPROVED:
        explanation = "An administrator approved your account request."
    elif template is EmailTemplate.ACCOUNT_REJECTED:
        explanation = "An administrator updated your account request. Contact your organization if you need help."
    elif template is EmailTemplate.MFA_FALLBACK:
        explanation = "Use this one-time code to verify your sign-in. If you did not request it, contact your administrator."
    elif template is EmailTemplate.ACCOUNT_EXISTS:
        explanation = "A sign-up request was made using this email address, but an account already exists. If you did not make this request, you can ignore this email."
    else:
        explanation = "The password for your account was changed. If you did not make this change, contact your administrator."

    if verification_code and template in {EmailTemplate.PASSWORD_RESET, EmailTemplate.VERIFY_EMAIL, EmailTemplate.MFA_FALLBACK}:
        explanation = "Use this one-time code to continue. It expires in 10 minutes. If you did not request it, ignore this email."

    action_label = "Accept invitation" if template is EmailTemplate.INVITATION else "Continue securely"
    action_text = f"\n{action_label}: {action_url}" if action_url else ""
    action_html = (
        f'<p style="margin:24px 0"><a href="{escape(action_url, quote=True)}" '
        'style="display:inline-block;background:#146EF5;color:#FFFFFF;padding:12px 18px;'
        'border-radius:8px;text-decoration:none;font-weight:600">'
        f"{escape(action_label)}</a></p>"
        if action_url
        else ""
    )
    code_text = f"\n\nYour one-time code: {verification_code}" if verification_code else ""
    code_html = (
        f'<p style="margin:24px 0;padding:14px 18px;border:1px solid #DCE7F3;border-radius:8px;'
        'background:#EAF5FF;color:#071A3D;font-size:26px;font-weight:700;letter-spacing:6px">'
        f"{escape(verification_code)}</p>"
        if verification_code
        else ""
    )
    text = f"{heading}\n\n{text_greeting}\n\n{explanation}{code_text}{action_text}\n\nIf you did not request this, ignore this email.\n\nCognate AI"
    html_body = (
        '<!doctype html><html><body style="margin:0;background:#F5FAFF;font-family:Arial,sans-serif;color:#071A3D">'
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#F5FAFF;padding:24px 8px">'
        '<tr><td align="center"><table role="presentation" width="560" cellspacing="0" cellpadding="0" '
        'style="max-width:560px;width:100%;background:#FFFFFF;border:1px solid #DCE7F3;border-radius:12px">'
        '<tr><td style="padding:24px 28px;background:#071A3D;color:#FFFFFF;font-weight:700">COGNATE AI</td></tr>'
        '<tr><td style="padding:28px"><h1 style="font-size:22px;margin:0 0 20px">'
        f"{escape(heading)}</h1><p>{html_greeting}</p><p style=\"line-height:1.6\">{escape(explanation)}</p>"
        f"{code_html}{action_html}<p style=\"font-size:13px;color:#52627A;line-height:1.5\">If you did not request this, ignore this email.</p>"
        '</td></tr></table></td></tr></table></body></html>'
    )
    return RenderedEmail(subject=subject, text=text, html=html_body)
