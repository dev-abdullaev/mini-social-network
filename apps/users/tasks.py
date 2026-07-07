from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from .models import User


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def send_verification_email(self, user_id, token):
    user = User.objects.filter(pk=user_id).first()
    if user is None:
        return
    verify_url = f"{settings.SITE_URL}/api/auth/verify-email/?token={token}"
    try:
        send_mail(
            subject="Emailingizni tasdiqlang",
            message=(
                f"Salom {user.username},\n\n"
                f"Emailingizni tasdiqlash uchun quyidagi havolani oching:\n{verify_url}\n\n"
                f"Havola {settings.VERIFICATION_TOKEN_TTL_HOURS} soatdan so'ng eskiradi."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
        )
    except Exception as exc:
        raise self.retry(exc=exc) from exc


@shared_task
def cleanup_unverified_users():
    cutoff = timezone.now() - timedelta(hours=settings.UNVERIFIED_USER_TTL_HOURS)
    pks = list(
        User.objects.filter(is_verified=False, is_staff=False, created_at__lt=cutoff).values_list(
            "pk", flat=True
        )
    )
    for i in range(0, len(pks), 500):
        User.objects.filter(pk__in=pks[i : i + 500]).delete()
    return len(pks)
