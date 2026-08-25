"""F3 — Google Workspace SSO domain gate + no-auto-provision (fail-closed).

django-allauth runs Google OAuth alongside Horilla's native CompanyScopedBackend
(kept in AUTHENTICATION_BACKENDS), so the superuser can always log in natively
even if SSO breaks — that structural coexistence is the lockout safety, which is
why no feature flag is needed.

Two fail-closed gates, enforced in ``pre_social_login`` (the ``hd`` OAuth param
is only a UI hint, not security):
  1. Email domain must be in ALLOWED_SSO_DOMAINS (default @aidachip.com only).
  2. The email must already map to an existing user/Employee — a first-time
     @aidachip.com login with no Employee is REJECTED, not auto-provisioned
     (auto-provision grants access from any workspace account; that is a
     privilege decision left to an admin, plan §10b / Amin).
"""

import logging

from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied

logger = logging.getLogger(__name__)

DEFAULT_ALLOWED_DOMAINS = ("aidachip.com",)


def allowed_domains() -> tuple[str, ...]:
    return tuple(getattr(settings, "ALLOWED_SSO_DOMAINS", DEFAULT_ALLOWED_DOMAINS))


def email_domain_allowed(email: str | None) -> bool:
    """True only for a well-formed email in an allowed domain. Default-deny."""
    if not email or "@" not in email:
        return False
    domain = email.rsplit("@", 1)[1].lower().strip()
    return domain in {d.lower() for d in allowed_domains()}


def existing_user_for(email: str):
    """Return the existing user for ``email`` (case-insensitive), or None.

    A matching user is created for every Employee by Horilla, so "no user" means
    "no staff record" -> deny (no auto-provision).
    """
    if not email:
        return None
    return get_user_model().objects.filter(email__iexact=email).first()


class AidaSocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        email = (sociallogin.user.email or "").strip()

        if not email_domain_allowed(email):
            logger.warning("SSO rejected: disallowed domain for %r", email)
            raise PermissionDenied("Sign-in restricted to AIDAChip staff accounts.")

        existing = existing_user_for(email)
        if existing is None:
            logger.warning("SSO rejected: no Employee/user for %r", email)
            raise PermissionDenied(
                "No AIDAChip staff account exists for this email."
            )

        # Link the Google identity to the existing staff user (no duplicate).
        if not sociallogin.is_existing:
            sociallogin.connect(request, existing)

    def is_open_for_signup(self, request, sociallogin):
        # Never let allauth create a brand-new account from SSO — linking to an
        # existing user happens in pre_social_login; anything else is denied.
        return False


class AidaAccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        # Native self-signup stays closed; native /login for existing staff
        # (superuser included) is unaffected.
        return False
