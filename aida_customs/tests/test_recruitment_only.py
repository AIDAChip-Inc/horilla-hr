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
        """Fail-closed witness: every installed non-recruitment HRMS feature app
        maps to a blocked URL segment. An upstream-added feature app turns this
        red instead of silently leaking a new HRMS surface."""
        from django.conf import settings

        installed = set(settings.INSTALLED_APPS)
        for app, segment in middleware.FEATURE_APP_SEGMENTS.items():
            if app in installed:
                with self.subTest(app=app):
                    self.assertIn(
                        segment,
                        middleware.BLOCKED_SEGMENTS,
                        f"HRMS app '{app}' installed but segment '{segment}' not gated",
                    )
        # KILL-NOTE: drop "payroll" from BLOCKED_SEGMENTS -> RED.
