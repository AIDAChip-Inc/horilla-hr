"""F5 — strip the deploy to recruitment-only.

Every HRMS feature app in Horilla self-registers its routes under its **own**
first-path-segment prefix (``payroll/``, ``leave/``, ``attendance/`` … — see
each app's ``apps.py`` ``ready()``), while ``recruitment`` mounts under
``recruitment/`` and ``base`` owns the root ("") namespace (login, dashboard
shell, notifications, company switch). So the gate is a **prefix denylist**
keyed on the leading path segment: a request into a blocked HRMS segment
returns **404** (404, not 403 — it does not advertise the module exists);
everything else — the ``base`` shell, ``/recruitment/`` (staff pipeline AND the
public candidate pages), auth, static, our ``/aida/`` routes — passes through.

Why prefix and not the resolved view's app: most HRMS views are wrapped by
decorators defined in ``horilla.decorators`` / ``horilla_views``, so the
resolved view's ``__module__`` is the decorator's module, not the feature
app's — resolving by module leaks (a ``/payroll/settings/`` view reports
``horilla.decorators``). The mount prefix is the app's own and does not lie.

Public candidate pages (``/recruitment/open-recruitments/``,
``/recruitment/application-form/``, ``/recruitment/candidate-self-tracking/``)
live under ``recruitment/`` and carry no ``login_required`` upstream, so this
gate leaves them reachable without auth — reachability is decided here, *who*
is still decided by Horilla's own per-view auth decorators.

Fail-closed at the witness: ``test_recruitment_only`` recomputes the installed
HRMS-feature-app set from ``settings`` and asserts each is gated, so a feature
app arriving from an upstream merge turns the suite red rather than silently
leaking a new HRMS surface.
"""

from django.http import Http404

# Leading path segments of the non-recruitment HRMS feature apps. Each app
# mounts its own routes under exactly this segment (its ``apps.py`` ready()).
# recruitment/ is deliberately absent (kept); base's root "" is never blocked.
BLOCKED_SEGMENTS = frozenset(
    {
        "payroll",
        "leave",
        "attendance",
        "asset",
        "pms",
        "onboarding",
        "offboarding",
        "project",
        "helpdesk",
        "report",
        "meet",        # horilla_meet
        "backup",      # horilla_backup
        "whatsapp",
        "biometric",
    }
)

# Maps an installed app label -> the URL segment it mounts under, for the
# drift guard in the tests (app labels differ from their URL prefixes).
FEATURE_APP_SEGMENTS = {
    "payroll": "payroll",
    "leave": "leave",
    "attendance": "attendance",
    "asset": "asset",
    "pms": "pms",
    "onboarding": "onboarding",
    "offboarding": "offboarding",
    "project": "project",
    "helpdesk": "helpdesk",
    "report": "report",
    "horilla_meet": "meet",
    "horilla_backup": "backup",
    "whatsapp": "whatsapp",
    "biometric": "biometric",
}


def _leading_segment(path: str) -> str:
    """First path segment of ``path`` ("/payroll/x/" -> "payroll"), or ""."""
    stripped = path.strip("/")
    return stripped.split("/", 1)[0] if stripped else ""


def is_blocked(path: str) -> bool:
    """True when ``path``'s leading segment is a blocked HRMS feature app."""
    return _leading_segment(path) in BLOCKED_SEGMENTS


class RecruitmentOnlyMiddleware:
    """404 any route under a non-recruitment HRMS feature-app prefix."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if is_blocked(request.path_info):
            raise Http404("Not available on the recruitment-only deployment.")
        return self.get_response(request)
