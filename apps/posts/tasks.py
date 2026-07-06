from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from .models import Post


@shared_task
def cleanup_old_posts():
    days = settings.POST_TTL_DAYS
    if not days:
        return 0
    cutoff = timezone.now() - timedelta(days=days)
    stale = Post.objects.filter(created_at__lt=cutoff)
    count = stale.count()
    stale.delete()
    return count
