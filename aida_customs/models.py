"""F1 — blind interview scorecards + candidate discussion.

Two additive tables. Neither extends nor rewrites any Horilla core model
(``CandidateRating`` is score-only with no submit-state; ``StageNote`` is a
flat ungated note) — so there is no blue-green migration and no core patch.

The single submit-state on ``InterviewScorecard`` gates THREE surfaces (reading
other interviewers' scorecards, reading the candidate discussion, posting to
it). That gate lives in ``aida_customs/visibility.py`` — never in a template or
a view. Both models carry ``company_id`` as the tenant co-key.
"""

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from base.horilla_company_manager import HorillaCompanyManager
from horilla.models import HorillaModel


class ScorecardState(models.TextChoices):
    DRAFT = "draft", "Draft"
    SUBMITTED = "submitted", "Submitted"


class Recommendation(models.TextChoices):
    STRONG_NO = "strong_no", "Strong No"
    NO = "no", "No"
    YES = "yes", "Yes"
    STRONG_YES = "strong_yes", "Strong Yes"


class InterviewScorecard(HorillaModel):
    """One interviewer's blinded review of one interview.

    ``state`` defaults to DRAFT — the fail-closed default: a row that exists but
    was never explicitly submitted counts as not-submitted, so its author sees
    no one else's feedback and cannot enter the discussion.
    """

    interview = models.ForeignKey(
        "recruitment.InterviewSchedule",
        on_delete=models.CASCADE,
        related_name="scorecards",
    )
    interviewer = models.ForeignKey("employee.Employee", on_delete=models.CASCADE)
    score = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(5)]
    )
    feedback = models.TextField()  # the narrative the blind gate protects
    recommendation = models.CharField(
        max_length=16, choices=Recommendation.choices
    )
    state = models.CharField(
        max_length=16,
        choices=ScorecardState.choices,
        default=ScorecardState.DRAFT,
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    company_id = models.ForeignKey(
        "base.Company", on_delete=models.CASCADE, verbose_name="Company"
    )

    objects = HorillaCompanyManager("company_id")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["interview", "interviewer"],
                name="uq_scorecard_interview_interviewer",
            )
        ]

    def __str__(self) -> str:
        return f"Scorecard {self.interviewer_id} / interview {self.interview_id} ({self.state})"


class CandidateDiscussionComment(HorillaModel):
    """Staff-internal threaded discussion about a candidate.

    Gated by the SAME submit-state as scorecards (borrowed entirely — the
    discussion has no state of its own, so the two switches can never disagree).
    Not candidate-visible: there is deliberately no ``candidate_can_view`` flag.
    """

    candidate = models.ForeignKey(
        "recruitment.Candidate",
        on_delete=models.CASCADE,
        related_name="discussion",
    )
    author = models.ForeignKey("employee.Employee", on_delete=models.CASCADE)
    body = models.TextField()
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="replies",
    )
    company_id = models.ForeignKey(
        "base.Company", on_delete=models.CASCADE, verbose_name="Company"
    )

    objects = HorillaCompanyManager("company_id")

    def __str__(self) -> str:
        return f"Comment {self.pk} by {self.author_id} on candidate {self.candidate_id}"
