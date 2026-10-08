import pytest

from app.config import settings
from app.services import email_provider
from app.services.email_templates import EmailTemplate, render_email


@pytest.mark.parametrize("template", list(EmailTemplate))
def test_every_auth_email_template_has_text_and_html(template):
    url = "https://example.test/action?token=synthetic&return=<script>"
    rendered = render_email(template, display_name="A <Synthetic> User", action_url=url)
    assert rendered.subject
    assert "Hello A <Synthetic> User," in rendered.text
    assert "&lt;Synthetic&gt;" in rendered.html
    assert url in rendered.text
    assert url not in rendered.html
    assert "token=synthetic&amp;return=&lt;script&gt;" in rendered.html
    assert "<script>" not in rendered.html
    assert "tracking" not in rendered.html.lower()


def test_template_rejects_non_http_action_urls():
    with pytest.raises(ValueError):
        render_email(EmailTemplate.PASSWORD_RESET, action_url="javascript:alert(1)")


def test_action_links_open_existing_frontend_routes(monkeypatch):
    monkeypatch.setattr(settings, "public_app_url", "http://localhost:8443/")
    reset = email_provider.action_link("password-reset", "synthetic-token")
    invite = email_provider.action_link("invite-accept", "synthetic-token")
    assert reset == "http://localhost:8443/reset-password?token=synthetic-token"
    assert invite == "http://localhost:8443/accept-invitation?token=synthetic-token"


def test_email_readiness_requires_a_valid_public_link_origin(monkeypatch):
    monkeypatch.setattr(email_provider, "configured_email_provider", lambda: object())
    monkeypatch.setattr(settings, "public_app_url", "https://mdis.example.test")
    assert email_provider.email_delivery_available() is True
    monkeypatch.setattr(settings, "public_app_url", "javascript:alert(1)")
    assert email_provider.email_delivery_available() is False


@pytest.mark.asyncio
async def test_delivery_retries_without_logging_message_data(monkeypatch):
    class Provider:
        def __init__(self):
            self.attempts = 0

        async def send(self, recipient, subject, body, html_body=None):
            self.attempts += 1
            if self.attempts == 1:
                raise RuntimeError("synthetic provider failure")

    provider = Provider()
    monkeypatch.setattr(email_provider, "configured_email_provider", lambda: provider)
    monkeypatch.setattr(settings, "email_retry_attempts", 2)
    monkeypatch.setattr(settings, "email_retry_backoff_seconds", 0)
    result = await email_provider.send_templated_email("synthetic@example.test", EmailTemplate.SECURITY_ALERT)
    assert result is True
    assert provider.attempts == 2


@pytest.mark.asyncio
async def test_delivery_returns_false_when_provider_is_not_configured(monkeypatch):
    monkeypatch.setattr(email_provider, "configured_email_provider", lambda: None)
    assert await email_provider.send_templated_email("synthetic@example.test", EmailTemplate.SECURITY_ALERT) is False


@pytest.mark.asyncio
async def test_verification_code_delivery_renders_code_through_configured_provider(monkeypatch):
    class Provider:
        captured = None

        async def send(self, recipient, subject, body, html_body=None):
            self.captured = (recipient, subject, body, html_body)

    provider = Provider()
    monkeypatch.setattr(email_provider, "configured_email_provider", lambda: provider)
    assert await email_provider.send_verification_code(
        "synthetic@example.test", "verify_email", "123456"
    ) is True
    assert provider.captured is not None
    recipient, subject, body, html_body = provider.captured
    assert recipient == "synthetic@example.test"
    assert "Verify your Cognate AI email" in subject
    assert "Your one-time code: 123456" in body
    assert ">123456</p>" in html_body
