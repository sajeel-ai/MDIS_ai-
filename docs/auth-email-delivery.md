# Authentication email delivery

## Local development with Mailpit

Mailpit is a local SMTP sink: the app sends mail to it, and it displays messages without delivering them to real recipients.

1. From the repository root, copy `.env.example` to `.env` and set a private URL-safe `POSTGRES_PASSWORD`. The Compose database password is required; no default is provided.
2. Start the local services with `docker compose up -d postgres mailpit backend`.
3. Open Mailpit at `http://localhost:8025`. Its SMTP listener is bound to `127.0.0.1:1025` on the host and port `1025` inside Compose.
4. Configure the backend's local `PUBLIC_APP_URL` to the frontend origin (Compose defaults to `http://localhost:8443`). Password reset and invitation actions appear in the Mailpit inbox. Their links target the existing `/reset-password` and `/accept-invitation` frontend routes.

The Compose override selects SMTP and disables STARTTLS only for the isolated Mailpit service. Do not copy those SMTP settings into a production deployment. Action links are never written to application logs.

## Production provider setup

Set `EMAIL_PROVIDER` to `smtp`, `resend`, or `sendgrid`; set `EMAIL_FROM`; then provide the corresponding SMTP host/port/user/password, `RESEND_API_KEY`, or `SENDGRID_API_KEY`. `SMTP_USER` is the preferred SMTP username name; `SMTP_USERNAME` remains accepted for existing deployments. Set `PUBLIC_APP_URL` to the exact public frontend origin. Delivery has a configured timeout, bounded retry count, and capped exponential backoff. Provider exceptions are not logged with message, address, credential, or response-body data.

Transactional messages use text and HTML alternatives with escaped display-name and URL values. They do not load remote images or include tracking pixels. Password-reset and invitation delivery is scheduled after the API response work; the reset endpoint remains generic for known and unknown accounts. If no provider is configured, password reset and enabled public registration return HTTP 503 with a global email-configuration message. Invitation creation reports `email_delivery: not_configured`, and the admin UI presents that state. Action links and provider response bodies are never logged.

## Domain authentication records

For the sending domain, configure records using the exact values supplied by the chosen mail provider:

- **SPF:** publish or update the domain's SPF TXT record with the provider's documented authorization mechanism. Keep one SPF record per domain and merge mechanisms rather than adding multiple SPF records.
- **DKIM:** publish the provider's selector records (usually CNAME or TXT) exactly as issued in its sending-domain setup.
- **DMARC:** add a TXT record at `_dmarc.<your-domain>`. Start with a monitoring policy such as `p=none` and an owned aggregate-report mailbox; review reports before moving to `quarantine` or `reject`.

Record values are provider- and domain-specific and are intentionally not fabricated here. Validate DNS propagation and provider verification before sending real account mail. Use synthetic accounts during local verification.
