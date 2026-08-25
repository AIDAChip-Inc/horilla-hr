"""
Optional integrations (e.g. AWS S3) layered on top of base settings.

Imported from horilla.settings.__init__ after base.py. Client overrides belong
in local_settings.py (imported after this module) — do not import them here.
"""

from .base import INSTALLED_APPS, MEDIA_ROOT, MEDIA_URL, MIDDLEWARE, env

if env("AWS_ACCESS_KEY_ID", default=None):
    AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY")
    AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME")
    AWS_S3_REGION_NAME = env("AWS_S3_REGION_NAME")
    DEFAULT_FILE_STORAGE = env("DEFAULT_FILE_STORAGE")
    AWS_S3_ADDRESSING_STYLE = env("AWS_S3_ADDRESSING_STYLE")

if env("AWS_ACCESS_KEY_ID", default=None) and "storages" not in INSTALLED_APPS:
    INSTALLED_APPS.append("storages")

if env("AWS_ACCESS_KEY_ID", default=None) and "storages" in INSTALLED_APPS:
    MEDIA_URL = f"{env('MEDIA_URL')}/{env('NAMESPACE')}/"
    MEDIA_ROOT = f"{env('MEDIA_ROOT')}/{env('NAMESPACE')}/"


# ===== AIDACHIP CUSTOMS (aida_customs) — keep in one block for clean upstream merges =====
# All AIDAChip customizations are layered here (settings) + the single
# ``aida_customs`` app. Core files ``horilla/settings/base.py`` and
# ``horilla/urls.py`` are never edited. See
# aidachip-knowledge/HORILLA_ATS_CUSTOMS_BUILD_PLAN.md.

# F4 — register the one custom app.
if "aida_customs" not in INSTALLED_APPS:
    INSTALLED_APPS.append("aida_customs")

# F5 — strip to recruitment-only.
#   (a) Route gate: block every non-recruitment HRMS feature app at the URL.
if "aida_customs.middleware.RecruitmentOnlyMiddleware" not in MIDDLEWARE:
    MIDDLEWARE.append("aida_customs.middleware.RecruitmentOnlyMiddleware")

#   (b) Nav gate: the main sidebar is built from settings.SIDEBARS
#       (horilla.config.sidebar iterates it). Trim to recruitment only, so no
#       HRMS module appears in navigation. Data-driven — no template override.
SIDEBARS = ["recruitment"]

#   (c) Land staff on the recruitment pipeline after login, never the HRMS home
#       dashboard (which aggregates payroll/attendance/leave widgets).
LOGIN_REDIRECT_URL = "/recruitment/pipeline/"
# ===== END AIDACHIP CUSTOMS =====
