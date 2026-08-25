"""F1 — scorecard state transitions (kept out of the visibility layer)."""

from django.utils import timezone

from aida_customs.models import InterviewScorecard, ScorecardState


def submit_scorecard(interviewer, interview) -> InterviewScorecard:
    """Flip ``interviewer``'s scorecard for ``interview`` DRAFT -> SUBMITTED.

    This is the single switch that opens all three blinded surfaces. One-way by
    default (un-submit is admin-only — founder decision, plan §10(c)); this
    helper never moves a row back to DRAFT.
    """
    card = InterviewScorecard.objects.get(
        interview=interview, interviewer=interviewer
    )
    if card.state != ScorecardState.SUBMITTED:
        card.state = ScorecardState.SUBMITTED
        card.submitted_at = timezone.now()
        card.save(update_fields=["state", "submitted_at"])
    return card
