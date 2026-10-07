"""
Outbound email — password reset and account-verification messages.

Uses the Resend HTTPS API instead of SMTP so the application can send
transactional email from Railway without requiring outbound SMTP access.
"""

import logging

import httpx

from app.config.settings import get_settings

logger = logging.getLogger("pairza.email")
settings = get_settings()

RESEND_API_URL = "https://api.resend.com/emails"


def send_email(to: str, subject: str, body: str) -> None:
    """
    Best-effort email delivery.

    Never raises to the caller. Email delivery failure must not turn an
    authentication/verification request into an unrelated server error.
    """

    if not settings.RESEND_API_KEY:
        logger.info(
            "Resend not configured — logging email instead of sending.\n"
            "To: %s\nSubject: %s\n\n%s",
            to,
            subject,
            body,
        )
        return

    payload = {
        "from": settings.RESEND_FROM_EMAIL,
        "to": [to],
        "subject": subject,
        "text": body,
    }

    headers = {
        "Authorization": f"Bearer {settings.RESEND_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=10) as client:
            response = client.post(
                RESEND_API_URL,
                headers=headers,
                json=payload,
            )

        if response.is_success:
            logger.info(
                "Email sent successfully to %s (subject: %r)",
                to,
                subject,
            )
        else:
            logger.error(
                "Resend rejected email to %s (status=%s): %s",
                to,
                response.status_code,
                response.text,
            )

    except Exception:
        logger.exception(
            "Failed to send email to %s (subject: %r)",
            to,
            subject,
        )