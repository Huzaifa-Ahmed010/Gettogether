import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import settings


def send_verification_code(recipient: str, code: str) -> None:
    send_email_code(
        recipient,
        code,
        subject="Verify your GetTogether email",
        purpose="email verification",
        expiry_minutes=settings.email_otp_expire_minutes,
    )


def send_password_reset_code(recipient: str, code: str) -> None:
    send_email_code(
        recipient,
        code,
        subject="Reset your GetTogether password",
        purpose="password reset",
        expiry_minutes=settings.password_reset_expire_minutes,
    )


def send_email_code(
    recipient: str,
    code: str,
    *,
    subject: str,
    purpose: str,
    expiry_minutes: int,
) -> None:
    if not settings.smtp_host or not settings.smtp_from_email:
        if settings.environment.lower() != "production" and settings.development_show_email_otp:
            return
        raise RuntimeError("Email delivery is not configured")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.smtp_from_email
    message["To"] = recipient
    message.set_content(
        f"Your GetTogether {purpose} code is {code}.\n\n"
        f"This code expires in {expiry_minutes} minutes. "
        "If you did not request this, you can ignore this email."
    )

    tls_context = ssl.create_default_context()
    if settings.smtp_use_ssl:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=tls_context, timeout=15) as server:
            if settings.smtp_username:
                server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(message)
        return

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
        server.ehlo()
        if settings.smtp_use_starttls:
            server.starttls(context=tls_context)
            server.ehlo()
        if settings.smtp_username:
            server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(message)
