"""F5 — the recruitment-only route gate (prefix denylist).

Discriminates in BOTH directions: a blocked HRMS route 404s, a recruitment
route is left reachable, and public candidate routes stay reachable without
auth. Each assertion goes red when the gate is bypassed (kill-note per test).
"""

from django.http import Http404, HttpResponse
from django.test import RequestFactory, SimpleTestCase

from aida_customs import middleware
from aida_customs.middleware import RecruitmentOnlyMiddleware, is_blocked


def _passthrough(request):
    return HttpResponse("ok")


class RouteGateTests(SimpleTestCase):
    def _status(self, path):
        # The middleware raises Http404 (Django's stack converts that to a 404
        # response); calling it directly, we convert the same way.
        mw = RecruitmentOnlyMiddleware(_passthrough)
        try:
            return mw(RequestFactory().get(path)).status_code
        except Http404:
            return 404

    def test_blocked_hrms_routes_404(self):
        # Real Horilla routes under blocked HRMS feature-app prefixes.
        for path in [
            "/payroll/view-payslip/",
            "/attendance/attendance-view/",
            "/asset/asset-category-view/",
            "/pms/objective-list-view/",
            "/onboarding/onboarding-view/",
            "/leave/leave-dashboard/",
            "/api/facedetection/",  # /api/-mounted HRMS helper, gated by prefix
            "/api/geofencing/",
        ]:
            with self.subTest(path=path):
                self.assertTrue(is_blocked(path), f"{path} must be gated")
                self.assertEqual(self._status(path), 404)
        # KILL-NOTE: make __call__ return get_response(request) unconditionally
        # (or empty BLOCKED_SEGMENTS) -> these become 200 -> RED.

    def test_recruitment_route_reachable(self):
        path = "/recruitment/pipeline/"
        self.assertFalse(is_blocked(path))
        self.assertEqual(self._status(path), 200)  # passthrough, not 404
        # KILL-NOTE: add "recruitment" to BLOCKED_SEGMENTS -> 404 -> RED.

    def test_public_candidate_pages_reachable_without_auth(self):
        # No auth is applied by this middleware; these must pass the gate.
        for path in [
            "/recruitment/open-recruitments/",
            "/recruitment/application-form/",
            "/recruitment/candidate-self-tracking/",
        ]:
            with self.subTest(path=path):
                self.assertFalse(is_blocked(path), f"{path} must stay open")
                self.assertEqual(self._status(path), 200)
        # KILL-NOTE: add "recruitment" to BLOCKED_SEGMENTS -> public pages 404 -> RED.

    def test_base_shell_and_root_not_blocked(self):
        # base owns the root namespace; the shell must survive the gate.
        for path in ["/", "/settings/", "/employee/employee-view/"]:
            with self.subTest(path=path):
                self.assertFalse(is_blocked(path))
        # KILL-NOTE: block the "" segment -> root 404 -> RED (shell dead).

    def test_drift_guard_installed_hrms_apps_are_gated(self):
        """Fail-closed witness over the ACTUAL installed set: every installed app
        that is neither on the reachable allowlist nor gated is reported. A new
        upstream app (HRMS or otherwise) that is installed but not classified
        turns this red — unlike the old tautology which only iterated the gate's
        own map and could never fail."""
        from django.conf import settings

        ungated = _ungated_apps(settings.INSTALLED_APPS)
        self.assertEqual(
            ungated, [], f"installed apps neither allowlisted nor gated: {ungated}"
        )
        # KILL-NOTE: drop "payroll" from FEATURE_APP_SEGMENTS -> payroll is
        # installed, not allowlisted, no longer gated -> reported -> RED.

    def test_drift_guard_catches_a_new_ungated_app(self):
        """Discrimination proof without editing the gate: inject a brand-new HRMS
        app into INSTALLED_APPS and confirm the guard flags it."""
        new_installed = list(_dummy_settings_installed()) + ["payroll_v2_hrms"]
        self.assertIn("payroll_v2_hrms", _ungated_apps(new_installed))
        # An allowlisted or gated app in the same list is NOT flagged:
        self.assertNotIn("recruitment", _ungated_apps(new_installed))
        self.assertNotIn("payroll", _ungated_apps(new_installed))


# --- drift-guard helpers -----------------------------------------------------

# Apps that are legitimately reachable on the recruitment-only deploy:
# recruitment itself, the load-bearing base/employee shell, and the horilla_*
# infra + third-party libs. Anything installed and NOT here MUST be gated;
# a new, unclassified app trips the drift guard (fail-closed).
ALLOWED_UNGATED = frozenset(
    {
        "base",
        "employee",
        "recruitment",
        "accessibility",
        "horilla_auth",
        "horilla_theme",
        "horilla_audit",
        "horilla_widgets",
        "horilla_crumbs",
        "horilla_documents",
        "horilla_views",
        "horilla_automations",
        "horilla_api",
        "horilla_dbtemplate",
        "horilla_tour",
        "horilla_ldap",  # LDAP config, mounts at root "" — infra, not an HRMS surface
        "notifications",
        "mathfilters",
        "corsheaders",
        "simple_history",
        "django_filters",
        "widget_tweaks",
        "auditlog",
        "django_apscheduler",
        "rest_framework",
        "rest_framework_simplejwt",
        "drf_yasg",
        "aida_customs",
    }
)


def _is_reachable_allowlisted(app: str) -> bool:
    return (
        app in ALLOWED_UNGATED or app.startswith("django.") or app.startswith("allauth")
    )


def _is_gated(app: str) -> bool:
    """True when ``app`` is gated — by leading segment or by /api/ path prefix."""
    segment = middleware.FEATURE_APP_SEGMENTS.get(app)
    if segment is not None and segment in middleware.BLOCKED_SEGMENTS:
        return True
    prefix = middleware.FEATURE_APP_PATH_PREFIXES.get(app)
    return prefix is not None and prefix in middleware.BLOCKED_PATH_PREFIXES


def _ungated_apps(installed) -> list:
    """Installed apps that are neither allowlisted-reachable nor gated."""
    return [
        app
        for app in installed
        if not _is_reachable_allowlisted(app) and not _is_gated(app)
    ]


def _dummy_settings_installed():
    from django.conf import settings

    return settings.INSTALLED_APPS
