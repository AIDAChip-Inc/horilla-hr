"""AppConfig for aida_customs.

Follows the fork's own URL-registration idiom (each app appends its routes to
``horilla.urls.urlpatterns`` in ``ready()``), so ``horilla/urls.py`` itself is
never patched. The only core-file change is the marked block in
``horilla/settings/addons.py``.
"""

from django.apps import AppConfig


class AidaCustomsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "aida_customs"
    verbose_name = "AIDAChip Customs"

    def ready(self):
        from django.urls import include, path

        from horilla.urls import urlpatterns

        # F2: interview-scheduled -> ICS email signal.
        from aida_customs import signals  # noqa: F401

        # Our own routes (F1 discussion/scorecards views).
        urlpatterns.append(path("aida/", include("aida_customs.urls")))

        # F3: allauth routes, only when allauth is installed (added in the
        # marked settings block). Mounted alongside Horilla's native
        # /accounts/ auth urls — subpaths do not collide.
        from django.conf import settings

        if "allauth" in settings.INSTALLED_APPS:
            urlpatterns.append(path("accounts/", include("allauth.urls")))

        super().ready()
