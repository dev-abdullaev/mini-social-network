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
    pks = list(Post.objects.filter(created_at__lt=cutoff).values_list("pk", flat=True))
    for i in range(0, len(pks), 500):
        Post.objects.filter(pk__in=pks[i : i + 500]).delete()
    return len(pks)
