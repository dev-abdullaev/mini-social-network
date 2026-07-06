from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail

from .models import User


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def send_verification_email(self, user_id, token):
    user = User.objects.filter(pk=user_id).first()
    if user is None:
        return
    verify_url = f"{settings.SITE_URL}/api/auth/verify-email/?token={token}"
    try:
        send_mail(
            subject="Verify your email",
            message=(
                f"Hi {user.username},\n\n"
                f"Confirm your email by opening this link:\n{verify_url}\n\n"
                f"The link expires in {settings.VERIFICATION_TOKEN_TTL_HOURS} hours."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
        )
    except Exception as exc:
        raise self.retry(exc=exc) from exc
