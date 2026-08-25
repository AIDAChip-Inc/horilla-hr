"""F3 — Google SSO domain gate + no-auto-provision (fail-closed).

Discriminates: a non-@aidachip.com login is rejected and creates no account; an
@aidachip.com login with no Employee is rejected (no auto-provision); an
@aidachip.com login for an existing Employee links to it (no duplicate). Goes
red if the domain check or the existing-user check is removed.
"""

from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.contrib.auth import get_user_model
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase

from aida_customs.auth.adapter import (
    AidaSocialAccountAdapter,
    email_domain_allowed,
    existing_user_for,
)
from aida_customs.tests import _factories as f


def _sociallogin(email):
    user = get_user_model()(email=email, username=email)
    account = SocialAccount(provider="google", uid=email, extra_data={"email": email})
    return SocialLogin(user=user, account=account)


def _request():
    req = RequestFactory().get("/accounts/google/login/callback/")
    SessionMiddleware(lambda r: None).process_request(req)
    req.session.save()
    return req


class SsoDomainGateTests(TestCase):
    def setUp(self):
        self.adapter = AidaSocialAccountAdapter()

    def test_domain_helper_both_directions(self):
        self.assertTrue(email_domain_allowed("staff@aidachip.com"))
        self.assertFalse(email_domain_allowed("attacker@gmail.com"))
        self.assertFalse(email_domain_allowed(None))
        self.assertFalse(email_domain_allowed("no-at-sign"))

    def test_non_aidachip_google_login_rejected(self):
        with self.assertRaises(PermissionDenied):
            self.adapter.pre_social_login(_request(), _sociallogin("attacker@gmail.com"))
        self.assertEqual(
            get_user_model().objects.filter(email="attacker@gmail.com").count(), 0
        )

    def test_domain_gate_rejects_even_when_user_exists(self):
        # Independent witness for the DOMAIN check: a non-allowed domain that
        # DOES have an existing user must still be rejected — so removing the
        # domain check (and only that) makes this go red, unmasked by the
        # no-Employee gate.
        f.make_employee(f.make_company(), email="mole@evil.com")
        with self.assertRaises(PermissionDenied):
            self.adapter.pre_social_login(_request(), _sociallogin("mole@evil.com"))
        # KILL-NOTE: drop the email_domain_allowed check -> this links instead
        # of raising -> RED.

    def test_aidachip_login_without_employee_rejected(self):
        # No Employee/user exists for this @aidachip.com address.
        with self.assertRaises(PermissionDenied):
            self.adapter.pre_social_login(_request(), _sociallogin("ghost@aidachip.com"))
        # KILL-NOTE: drop the existing_user_for None check -> auto-provision
        # allowed -> no raise -> RED.

    def test_aidachip_login_links_existing_employee(self):
        emp = f.make_employee(f.make_company(), email="alice@aidachip.com")
        existing = emp.employee_user_id
        self.assertIsNotNone(existing_user_for("alice@aidachip.com"))
        sl = _sociallogin("alice@aidachip.com")
        # Must NOT raise, and must link to the existing user (no duplicate).
        self.adapter.pre_social_login(_request(), sl)
        self.assertEqual(sl.user.pk, existing.pk)
        self.assertEqual(
            get_user_model().objects.filter(email__iexact="alice@aidachip.com").count(),
            1,
        )
        # KILL-NOTE: make pre_social_login raise for allowed staff -> RED.
