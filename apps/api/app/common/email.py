"""
Outbound email — password reset and account-recovery messages only.

Stdlib-only (smtplib + email), so no new dependency for one feature. If SMTP
isn't configured (SMTP_HOST empty, the default), the message is logged
instead of sent — local development and this project's own sandboxed build
environment both work without real credentials, and a broken or slow SMTP
server can never turn into a 500 on a user-facing endpoint (send_email never
raises; see the try/except below).
"""
import logging
import smtplib
from email.message import EmailMessage

from app.config.settings import get_settings

logger = logging.getLogger("pairza.email")
settings = get_settings()


def send_email(to: str, subject: str, body: str) -> None:
    """Best-effort send. Never raises: a caller (e.g. the forgot-password endpoint) must not
    fail the whole request just because outbound mail is unavailable — and letting an SMTP
    error surface as a different HTTP response than the "email not found" case would itself
    leak whether an address is registered."""
    if not settings.SMTP_HOST:
        logger.info("SMTP not configured — logging email instead of sending.\nTo: %s\nSubject: %s\n\n%s", to, subject, body)
        return

    message = EmailMessage()
    message["From"] = settings.SMTP_FROM_EMAIL
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as smtp:
            if settings.SMTP_USE_TLS:
                smtp.starttls()
            if settings.SMTP_USERNAME:
                smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            smtp.send_message(message)
    except Exception:
        logger.exception("Failed to send email to %s (subject: %r)", to, subject)
