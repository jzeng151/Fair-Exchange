"""Static files storage whose URLs follow the per-request script prefix (exchange/middleware.py).

Django's storage reads STATIC_URL once, so on its own {% static %} would always give "/static/...". This makes it
"./static/..." on / and "../../static/..." on /chat/x/, which resolves behind any path proxy.
"""
from django.conf import settings
from django.urls import get_script_prefix
from whitenoise.storage import CompressedManifestStaticFilesStorage


class RelativeStaticFilesStorage(CompressedManifestStaticFilesStorage):
    def url(self, name, force=False):
        url = super().url(name, force)
        prefix = get_script_prefix()
        if settings.FORCE_SCRIPT_NAME or prefix == "/" or not url.startswith("/"):
            return url  # URL_PREFIX already put the prefix in STATIC_URL, or no request prefix applies
        return prefix + url.lstrip("/")
