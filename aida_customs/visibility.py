"""F1 — the blind-visibility gate. The ONE place blind access is decided.

Every read of scorecards, and every read/post of the candidate discussion,
routes through a function here. Views and templates never query
``InterviewScorecard`` / ``CandidateDiscussionComment`` directly.

The rules (founder-decided):
  * An INTERVIEWER sees only their OWN scorecard, and can neither read nor post
    in the discussion, until they SUBMIT their own scorecard. Submitting flips
    all three surfaces open at once.
  * A MANAGER (recruitment/stage manager or Django superuser) sees ALL
    scorecards and the discussion ALWAYS — they are not subject to the submit
    gate (they typically never submit a scorecard).
  * Anyone else (NONE) is denied everything.

Fail-closed: any ambiguity — unresolved role, missing own row, half-written
submit-state — hides. There is no path where an unresolved state returns
another interviewer's rows or lets a not-yet-submitted interviewer read/post.
Every query co-filters ``company_id`` (resolved from server-side relations,
never client input) so a company-A viewer can never reach a company-B row.
"""

from enum import Enum

from django.core.exceptions import PermissionDenied
from django.db.models import QuerySet

from aida_customs.models import (
    CandidateDiscussionComment,
    InterviewScorecard,
    ScorecardState,
)


class Role(Enum):
    NONE = "none"
    INTERVIEWER = "interviewer"
    MANAGER = "manager"


# ----------------------------------------------------------------------------
# Tenant co-key (server-resolved from the VIEWER, never from the accessed object
# or client input). Keying the read filter on the viewer's own company is
# defense-in-depth: even if a scorecard/interview row is mis-linked to another
# company by a data bug, a viewer can only ever see rows in THEIR company.
# ----------------------------------------------------------------------------


def _viewer_company(viewer):
    """The viewer's company (employee work-info). None -> deny (fail closed)."""
    return viewer.get_company() if viewer is not None else None


def _company_for_candidate(candidate):
    """Tenant a NEW discussion comment is stored under (the candidate's own)."""
    return candidate.recruitment_id.company_id


# ----------------------------------------------------------------------------
# Role resolution — default-deny
# ----------------------------------------------------------------------------


def _is_superuser(viewer) -> bool:
    user = getattr(viewer, "employee_user_id", None)
    return bool(user is not None and getattr(user, "is_superuser", False))


def _manages_recruitment(viewer, recruitment) -> bool:
    if recruitment is None:
        return False
    if recruitment.recruitment_managers.filter(pk=viewer.pk).exists():
        return True
    # Stage managers of any stage in this recruitment also manage the loop.
    return recruitment.stage_set.filter(stage_managers=viewer).exists()


def resolve_role(viewer, interview) -> Role:
    """Role of ``viewer`` relative to a single interview. Default-deny."""
    if viewer is None or interview is None:
        return Role.NONE
    recruitment = interview.candidate_id.recruitment_id
    if _is_superuser(viewer) or _manages_recruitment(viewer, recruitment):
        return Role.MANAGER
    if interview.employee_id.filter(pk=viewer.pk).exists():
        return Role.INTERVIEWER
    return Role.NONE


def resolve_role_for_candidate(viewer, candidate) -> Role:
    """Role of ``viewer`` relative to a candidate (spans their interviews)."""
    if viewer is None or candidate is None:
        return Role.NONE
    if _is_superuser(viewer) or _manages_recruitment(viewer, candidate.recruitment_id):
        return Role.MANAGER
    # Interviewer on any of this candidate's interviews.
    if candidate.candidate_interview.filter(employee_id=viewer).exists():
        return Role.INTERVIEWER
    return Role.NONE


# ----------------------------------------------------------------------------
# Scorecard gate
# ----------------------------------------------------------------------------


def visible_scorecards(*, viewer, interview) -> QuerySet:
    """Scorecards ``viewer`` may see for ``interview``. Default-deny."""
    viewer_company = _viewer_company(viewer)
    if viewer_company is None:
        return InterviewScorecard.objects.none()  # no company -> fail closed
    base = InterviewScorecard.objects.filter(
        interview=interview,
        company_id=viewer_company,  # keyed on the viewer, not the object
    )
    role = resolve_role(viewer, interview)
    if role == Role.NONE:
        return base.none()  # fail closed
    if role == Role.MANAGER:
        return base  # sees all, never gated
    # INTERVIEWER: only own until own is submitted.
    own = base.filter(interviewer=viewer)
    if own.filter(state=ScorecardState.SUBMITTED, submitted_at__isnull=False).exists():
        return base
    return own


# ----------------------------------------------------------------------------
# Discussion gate — the SAME switch, gates BOTH read and post
# ----------------------------------------------------------------------------


def has_finalized_for(viewer, candidate) -> bool:
    """True once ``viewer`` has SUBMITTED a scorecard on any of this candidate's
    interviews they are an interviewer on. Both state fields required."""
    viewer_company = _viewer_company(viewer)
    if viewer_company is None:
        return False  # no company -> fail closed
    return InterviewScorecard.objects.filter(
        interviewer=viewer,
        interview__candidate_id=candidate,
        state=ScorecardState.SUBMITTED,
        submitted_at__isnull=False,
        company_id=viewer_company,  # keyed on the viewer, not the object
    ).exists()


def can_access_discussion(*, viewer, candidate) -> bool:
    role = resolve_role_for_candidate(viewer, candidate)
    if role == Role.MANAGER:
        return True  # managers always in (see-all rule)
    if role == Role.INTERVIEWER:
        return has_finalized_for(viewer, candidate)  # gated by own submit
    return False  # NONE -> fail closed, no read, no post


def visible_discussion(*, viewer, candidate) -> QuerySet:
    if not can_access_discussion(viewer=viewer, candidate=candidate):
        return CandidateDiscussionComment.objects.none()  # read blocked -> empty
    viewer_company = _viewer_company(viewer)
    if viewer_company is None:
        return CandidateDiscussionComment.objects.none()  # fail closed
    return CandidateDiscussionComment.objects.filter(
        candidate=candidate, company_id=viewer_company  # keyed on the viewer
    )


def post_comment(*, author, candidate, body, parent=None) -> CandidateDiscussionComment:
    if not can_access_discussion(viewer=author, candidate=candidate):
        raise PermissionDenied(  # post blocked -> 403, fail closed
            "Submit your own scorecard before joining the discussion."
        )
    return CandidateDiscussionComment.objects.create(
        candidate=candidate,
        author=author,
        body=body,
        parent=parent,
        company_id=_company_for_candidate(candidate),
    )
