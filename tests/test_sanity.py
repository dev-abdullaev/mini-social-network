from django.conf import settings


def test_settings_load():
    assert "apps.core" in settings.INSTALLED_APPS
