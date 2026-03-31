from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_password_hash
from app.models import PasswordResetToken, User, UserSession


class PasswordResetError(Exception):
    pass


class PasswordResetProviderError(PasswordResetError):
    pass


_RESET_REQUEST_NEUTRAL_MESSAGE_RU = "Если аккаунт с такой почтой существует, мы отправили инструкции для восстановления."
_RESET_SUCCESS_MESSAGE_RU = "Пароль успешно обновлен."


class PasswordResetService:
    def request_password_reset(self, db: Session, *, email: str) -> str:
        """
        Безопасный endpoint: не раскрываем наличие email в системе.
        Всегда возвращаем нейтральное сообщение.
        """
        normalized_email = (email or "").strip().lower()
        if not normalized_email:
            # Считаем запрос неверным, чтобы не плодить токены с пустым email.
            raise PasswordResetError("Введите корректную почту.")

        user = db.scalar(select(User).where(func.lower(User.email) == normalized_email))
        if not user:
            return _RESET_REQUEST_NEUTRAL_MESSAGE_RU

        now = datetime.now(timezone.utc)
        cooldown_seconds = max(1, int(settings.password_reset_request_resend_cooldown_seconds))

        pending = db.scalar(
            select(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.consumed_at.is_(None),
                PasswordResetToken.expires_at > now,
            )
            .order_by(PasswordResetToken.created_at.desc())
            .limit(1)
        )
        if pending:
            seconds_from_last = int((now - pending.created_at).total_seconds())
            if seconds_from_last < cooldown_seconds:
                return _RESET_REQUEST_NEUTRAL_MESSAGE_RU

        token_raw = secrets.token_urlsafe(32)
        token_hash = self._hash_token(token_raw)
        ttl_minutes = max(1, int(settings.password_reset_token_ttl_minutes))
        expires_at = now + timedelta(minutes=ttl_minutes)

        reset_url = self._build_reset_url(token_raw)
        try:
            self._send_reset_email_via_resend(
                to_email=normalized_email,
                reset_url=reset_url,
                ttl_minutes=ttl_minutes,
            )
        except PasswordResetProviderError:
            # По безопасности/UX: не меняем ответ пользователю, даже если Resend упал.
            # И НЕ создаём токен в БД, чтобы следующий запрос мог повторно создать токен и отправить письмо.
            return _RESET_REQUEST_NEUTRAL_MESSAGE_RU

        # Обеспечиваем «1 token => 1 use» и предотвращаем рост числа активных токенов.
        db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id, PasswordResetToken.consumed_at.is_(None)))
        db.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=token_hash,
                created_at=now,
                expires_at=expires_at,
                consumed_at=None,
            )
        )
        db.commit()

        return _RESET_REQUEST_NEUTRAL_MESSAGE_RU

    def confirm_password_reset(self, db: Session, *, token: str, new_password: str) -> str:
        normalized_token = (token or "").strip()
        if not normalized_token:
            raise PasswordResetError("Неверный или истекший токен сброса пароля.")

        now = datetime.now(timezone.utc)
        token_hash = self._hash_token(normalized_token)
        reset_token = db.scalar(
            select(PasswordResetToken)
            .where(
                PasswordResetToken.token_hash == token_hash,
                PasswordResetToken.consumed_at.is_(None),
            )
            .order_by(PasswordResetToken.created_at.desc())
            .limit(1)
        )

        if not reset_token or reset_token.expires_at <= now:
            raise PasswordResetError("Неверный или истекший токен сброса пароля.")

        user = db.get(User, int(reset_token.user_id))
        if not user:
            raise PasswordResetError("Неверный или истекший токен сброса пароля.")

        user.password_hash = get_password_hash(new_password)
        reset_token.consumed_at = now

        # Инвалидация активных сессий: доступ и refresh перестанут работать.
        db.execute(
            update(UserSession)
            .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )

        db.commit()
        return _RESET_SUCCESS_MESSAGE_RU

    def _hash_token(self, token_raw: str) -> str:
        secret = settings.jwt_secret_key.strip() or "oku-dev-email-secret"
        payload = token_raw.encode("utf-8")
        return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()

    def _build_reset_url(self, token_raw: str) -> str:
        base = settings.frontend_app_url.strip() or "http://localhost:3000"
        # /reset-password?token=...
        return f"{base.rstrip('/')}/reset-password?token={token_raw}"

    def _send_reset_email_via_resend(self, *, to_email: str, reset_url: str, ttl_minutes: int) -> None:
        api_key = settings.resend_api_key.strip()
        from_email = settings.smtp_from_email.strip() or settings.smtp_username.strip()
        if not api_key or not from_email:
            raise PasswordResetProviderError("Resend не настроен. Укажите RESEND_API_KEY и SMTP_FROM_EMAIL.")

        # Минимальный шаблон письма, без раскрытия деталей токена/существования email.
        html = "\n".join(
            [
                "<p>Здравствуйте!</p>",
                "<p>Мы получили запрос на восстановление пароля для OKU.</p>",
                "<p>",
                f'<a href="{reset_url}" style="display:inline-block;background:#6a63f5;color:#fff;padding:10px 16px;border-radius:8px;text-decoration:none;">Сбросить пароль</a>',
                "</p>",
                f"<p>Ссылка действует {max(1, ttl_minutes)} минут.</p>",
                "<p>Если это были не вы — просто проигнорируйте письмо.</p>",
            ]
        )

        text = "\n".join(
            [
                "Здравствуйте!",
                "Мы получили запрос на восстановление пароля для OKU.",
                "",
                f"Сбросить пароль: {reset_url}",
                f"Ссылка действует {max(1, ttl_minutes)} минут.",
                "Если это были не вы — просто проигнорируйте письмо.",
            ]
        )

        payload = {
            "from": f"{settings.smtp_from_name} <{from_email}>",
            "to": [to_email],
            "subject": "Сброс пароля OKU",
            "html": html,
            "text": text,
        }

        url = f"{settings.resend_base_url.rstrip('/')}/emails"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        try:
            with httpx.Client(timeout=max(1, int(settings.resend_timeout_seconds))) as client:
                response = client.post(url, json=payload, headers=headers)
        except Exception as exc:  # noqa: BLE001
            raise PasswordResetProviderError("Не удалось подключиться к Resend.") from exc

        if response.status_code not in {200, 201, 202}:
            detail = ""
            try:
                detail_payload = response.json()
                if isinstance(detail_payload, dict):
                    detail = str(detail_payload.get("message") or detail_payload.get("error") or detail_payload.get("name") or "").strip()
            except Exception:  # noqa: BLE001
                detail = ""
            raise PasswordResetProviderError(f"Resend вернул ошибку отправки ({response.status_code}){': ' + detail if detail else ''}.")


password_reset_service = PasswordResetService()

