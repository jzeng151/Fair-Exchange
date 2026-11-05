"""Relative URLs, so the app works behind any path proxy (e.g. https://<host>/proxy/8000/) without configuration.

A path proxy forwards /proxy/8000/chat/x/ to the app as /chat/x/, so absolute links like /static/app.css would
skip the prefix. Instead, each request sets Django's script prefix to the way back to the app root from the
current page ("./" on /, "../../" on /chat/x/). Everything Django generates ({% url %}, {% static %}, redirects)
then comes out relative to the page, and resolves under whatever prefix the browser used. URL_PREFIX (settings
FORCE_SCRIPT_NAME), when set, takes over and this middleware does nothing.
"""
from django.conf import settings
from django.urls import set_script_prefix


class RelativeScriptPrefixMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not settings.FORCE_SCRIPT_NAME:
            depth = request.path_info.count("/") - 1  # "/" -> 0, "/about/" -> 1, "/chat/x/" -> 2
            set_script_prefix("../" * depth if depth > 0 else "./")
        return self.get_response(request)
