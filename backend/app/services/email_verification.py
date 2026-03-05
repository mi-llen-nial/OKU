from __future__ import annotations

import hashlib
import hmac
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import EmailVerificationCode, User

REGISTER_PURPOSE = "register"


class EmailVerificationError(Exception):
    pass


class EmailVerificationRateLimitError(EmailVerificationError):
    def __init__(self, retry_after_seconds: int):
        self.retry_after_seconds = max(1, retry_after_seconds)
        super().__init__("Слишком частая отправка кода.")


class EmailVerificationProviderError(EmailVerificationError):
    pass


class EmailVerificationService:
    def send_register_code(self, db: Session, email: str) -> int:
        normalized_email = email.strip().lower()
        if not normalized_email:
            raise EmailVerificationError("Введите корректную почту.")

        if db.scalar(select(User.id).where(User.email == normalized_email)):
            raise EmailVerificationError("Пользователь с такой почтой уже существует.")

        now = datetime.now(timezone.utc)
        pending = db.scalar(
            select(EmailVerificationCode)
            .where(
                EmailVerificationCode.email == normalized_email,
                EmailVerificationCode.purpose == REGISTER_PURPOSE,
                EmailVerificationCode.consumed_at.is_(None),
            )
            .order_by(EmailVerificationCode.created_at.desc())
            .limit(1)
        )
        if pending:
            seconds_from_last = int((now - pending.created_at).total_seconds())
            cooldown = settings.email_verification_resend_cooldown_seconds
            if seconds_from_last < cooldown:
                raise EmailVerificationRateLimitError(cooldown - seconds_from_last)

        code = f"{secrets.randbelow(1_000_000):06d}"
        try:
            self._send_email(normalized_email, code)
        except EmailVerificationProviderError:
            # Local/dev fallback: keep registration flow testable even when SMTP
            # credentials/policies are not ready yet.
            if settings.app_env.strip().lower() in {"development", "dev", "local"}:
                print(
                    "[OKU][EMAIL][DEV_FALLBACK] "
                    f"email={normalized_email} code={code} "
                    "Email provider is unavailable, code printed to logs."
                )
            else:
                raise

        ttl_minutes = max(1, settings.email_verification_code_ttl_minutes)
        expires_at = now + timedelta(minutes=ttl_minutes)

        existing_pending_codes = db.scalars(
            select(EmailVerificationCode).where(
                EmailVerificationCode.email == normalized_email,
                EmailVerificationCode.purpose == REGISTER_PURPOSE,
                EmailVerificationCode.consumed_at.is_(None),
            )
        ).all()
        for item in existing_pending_codes:
            db.delete(item)

        db.add(
            EmailVerificationCode(
                email=normalized_email,
                purpose=REGISTER_PURPOSE,
                code_hash=self._hash_code(email=normalized_email, purpose=REGISTER_PURPOSE, code=code),
                created_at=now,
                expires_at=expires_at,
                attempts=0,
            )
        )
        return ttl_minutes * 60

    def consume_register_code(self, db: Session, email: str, code: str) -> bool:
        normalized_email = email.strip().lower()
        normalized_code = code.strip()
        if not normalized_email or not normalized_code:
            return False

        now = datetime.now(timezone.utc)
        verification = db.scalar(
            select(EmailVerificationCode)
            .where(
                EmailVerificationCode.email == normalized_email,
                EmailVerificationCode.purpose == REGISTER_PURPOSE,
                EmailVerificationCode.consumed_at.is_(None),
            )
            .order_by(EmailVerificationCode.created_at.desc())
            .limit(1)
        )
        if not verification:
            return False

        if verification.expires_at <= now:
            return False

        if verification.attempts >= 5:
            return False

        expected_hash = self._hash_code(email=normalized_email, purpose=REGISTER_PURPOSE, code=normalized_code)
        if not hmac.compare_digest(verification.code_hash, expected_hash):
            verification.attempts += 1
            return False

        verification.consumed_at = now
        return True

    def _hash_code(self, *, email: str, purpose: str, code: str) -> str:
        secret = settings.jwt_secret_key.strip() or "oku-dev-email-secret"
        payload = f"{purpose}:{email}:{code}".encode("utf-8")
        return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()

    def _send_email(self, to_email: str, code: str) -> None:
        provider = settings.email_provider.strip().lower() or "smtp"
        if provider == "sendgrid":
            self._send_via_sendgrid(to_email=to_email, code=code)
            return
        if provider == "resend":
            self._send_via_resend(to_email=to_email, code=code)
            return
        self._send_via_smtp(to_email=to_email, code=code)

    def _send_via_smtp(self, to_email: str, code: str) -> None:
        from_email = settings.smtp_from_email.strip() or settings.smtp_username.strip()
        if not from_email or not settings.smtp_username.strip() or not settings.smtp_password.strip():
            raise EmailVerificationProviderError(
                "SMTP не настроен. Укажите SMTP_USERNAME, SMTP_PASSWORD и SMTP_FROM_EMAIL."
            )

        message = EmailMessage()
        message["Subject"] = "Код подтверждения OKU"
        message["From"] = f"{settings.smtp_from_name} <{from_email}>"
        message["To"] = to_email
        message.set_content(
            "\n".join(
                [
                    "Здравствуйте!",
                    "",
                    "Ваш код подтверждения для регистрации в OKU:",
                    f"{code}",
                    "",
                    f"Код действует {max(1, settings.email_verification_code_ttl_minutes)} минут.",
                    "Если это были не вы, просто проигнорируйте это письмо.",
                ]
            )
        )

        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as client:
                client.ehlo()
                if settings.smtp_starttls:
                    client.starttls()
                    client.ehlo()
                client.login(settings.smtp_username, settings.smtp_password)
                client.send_message(message)
        except Exception as exc:  # noqa: BLE001
            raise EmailVerificationProviderError("Не удалось отправить письмо с кодом подтверждения.") from exc

    def _send_via_sendgrid(self, *, to_email: str, code: str) -> None:
        api_key = settings.sendgrid_api_key.strip()
        from_email = settings.smtp_from_email.strip() or settings.smtp_username.strip()
        if not api_key or not from_email:
            raise EmailVerificationProviderError(
                "SendGrid не настроен. Укажите SENDGRID_API_KEY и SMTP_FROM_EMAIL."
            )

        payload = {
            "personalizations": [{"to": [{"email": to_email}]}],
            "from": {"email": from_email, "name": settings.smtp_from_name},
            "subject": "Код подтверждения OKU",
            "content": [
                {
                    "type": "text/plain",
                    "value": "\n".join(
                        [
                            "Здравствуйте!",
                            "",
                            "Ваш код подтверждения для регистрации в OKU:",
                            f"{code}",
                            "",
                            f"Код действует {max(1, settings.email_verification_code_ttl_minutes)} минут.",
                            "Если это были не вы, просто проигнорируйте это письмо.",
                        ]
                    ),
                }
            ],
        }
        url = f"{settings.sendgrid_base_url.rstrip('/')}/mail/send"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=settings.sendgrid_timeout_seconds) as client:
                response = client.post(url, json=payload, headers=headers)
        except Exception as exc:  # noqa: BLE001
            raise EmailVerificationProviderError("Не удалось подключиться к SendGrid.") from exc

        if response.status_code != 202:
            raise EmailVerificationProviderError(
                f"SendGrid вернул ошибку отправки ({response.status_code})."
            )

    def _send_via_resend(self, *, to_email: str, code: str) -> None:
        api_key = settings.resend_api_key.strip()
        from_email = settings.smtp_from_email.strip() or settings.smtp_username.strip()
        if not api_key or not from_email:
            raise EmailVerificationProviderError(
                "Resend не настроен. Укажите RESEND_API_KEY и SMTP_FROM_EMAIL."
            )

        payload = {
            "from": f"{settings.smtp_from_name} <{from_email}>",
            "to": [to_email],
            "subject": "Код подтверждения OKU",
            "text": "\n".join(
                [
                    "Здравствуйте!",
                    "",
                    "Ваш код подтверждения для регистрации в OKU:",
                    f"{code}",
                    "",
                    f"Код действует {max(1, settings.email_verification_code_ttl_minutes)} минут.",
                    "Если это были не вы, просто проигнорируйте это письмо.",
                ]
            ),
        }
        url = f"{settings.resend_base_url.rstrip('/')}/emails"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        try:
            with httpx.Client(timeout=settings.resend_timeout_seconds) as client:
                response = client.post(url, json=payload, headers=headers)
        except Exception as exc:  # noqa: BLE001
            raise EmailVerificationProviderError("Не удалось подключиться к Resend.") from exc

        if response.status_code not in {200, 201, 202}:
            detail = ""
            try:
                detail_payload = response.json()
                if isinstance(detail_payload, dict):
                    detail = str(
                        detail_payload.get("message")
                        or detail_payload.get("error")
                        or detail_payload.get("name")
                        or ""
                    ).strip()
            except Exception:  # noqa: BLE001
                detail = ""
            suffix = f": {detail}" if detail else ""
            raise EmailVerificationProviderError(
                f"Resend вернул ошибку отправки ({response.status_code}){suffix}."
            )


email_verification_service = EmailVerificationService()
