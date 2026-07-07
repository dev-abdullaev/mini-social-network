import uuid

from django.db import models


class UUIDModel(models.Model):
    """Abstract base with a UUID primary key."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class CreatedAtModel(models.Model):
    """Abstract base with a creation timestamp."""

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True


class TimeStampedModel(CreatedAtModel):
    """Abstract base with creation and modification timestamps."""

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
