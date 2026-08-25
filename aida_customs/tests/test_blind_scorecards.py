"""F1 kill-test #1 — blind scorecards.

Asserts the protected payload (another interviewer's feedback + score) is
ABSENT before the viewer submits and PRESENT after, in BOTH directions, and
that a manager sees all with no own scorecard. Not "the page renders".
"""

from django.test import TestCase
from django.utils import timezone

from aida_customs.actions import submit_scorecard
from aida_customs.models import ScorecardState
from aida_customs.tests import _factories as f
from aida_customs.visibility import visible_scorecards


def _serialize(qs):
    return [(c.interviewer_id, c.feedback, c.score) for c in qs]


class BlindScorecardTests(TestCase):
    def setUp(self):
        self.company = f.make_company()
        self.rec = f.make_recruitment(self.company)
        self.cand = f.make_candidate(self.rec)
        self.A = f.make_employee(self.company)
        self.B = f.make_employee(self.company)
        self.interview = f.make_interview(self.cand, interviewers=[self.A, self.B])
        # B has submitted a real review; A has only a draft.
        self.B_card = f.make_scorecard(
            self.interview, self.B, self.company,
            state=ScorecardState.SUBMITTED, feedback="B_SECRET_FEEDBACK",
            score=5, submitted_at=timezone.now(),
        )
        self.A_card = f.make_scorecard(
            self.interview, self.A, self.company, state=ScorecardState.DRAFT
        )

    def test_A_cannot_see_B_until_A_submits(self):
        before = visible_scorecards(viewer=self.A, interview=self.interview)
        self.assertNotIn(self.B_card, before)
        self.assertNotIn("B_SECRET_FEEDBACK", [s.feedback for s in before])
        self.assertNotIn(5, [s.score for s in before])
        self.assertEqual(list(before), [self.A_card])  # only own
        # KILL-NOTE: make the INTERVIEWER branch `return base` -> B leaks -> RED.

    def test_gate_flips_open_after_A_submits(self):
        submit_scorecard(self.A, self.interview)  # DRAFT -> SUBMITTED + ts
        after = visible_scorecards(viewer=self.A, interview=self.interview)
        self.assertIn(self.B_card, after)
        self.assertIn("B_SECRET_FEEDBACK", [s.feedback for s in after])
        self.assertIn(5, [s.score for s in after])
        # KILL-NOTE: make submit_scorecard not set state -> gate never flips ->
        # B stays hidden -> this (the control) goes RED, proving it does work.

    def test_manager_sees_all_with_no_own_scorecard(self):
        mgr = f.make_employee(self.company)
        self.rec.recruitment_managers.add(mgr)
        visible = visible_scorecards(viewer=mgr, interview=self.interview)
        self.assertIn(self.B_card, visible)
        self.assertIn(self.A_card, visible)
        # KILL-NOTE: break the MANAGER branch (return base.none()) -> RED.

    def test_stranger_sees_nothing(self):
        outsider = f.make_employee(self.company)  # not on interview, not manager
        self.assertEqual(
            list(visible_scorecards(viewer=outsider, interview=self.interview)), []
        )
        # KILL-NOTE: default the role fall-through to `return base` -> RED.

    def test_half_written_submit_state_is_treated_as_not_submitted(self):
        # state SUBMITTED but submitted_at missing -> must NOT flip the gate.
        self.A_card.state = ScorecardState.SUBMITTED
        self.A_card.submitted_at = None
        self.A_card.save(update_fields=["state", "submitted_at"])
        visible = visible_scorecards(viewer=self.A, interview=self.interview)
        self.assertNotIn(self.B_card, visible)  # still blind
        # KILL-NOTE: drop submitted_at__isnull=False from the .exists() -> RED.

    def test_tenant_isolation_company_b_cannot_be_seen(self):
        # A viewer resolved into company A can never see a company-B scorecard.
        other_co = f.make_company("OTHER")
        other_rec = f.make_recruitment(other_co)
        other_cand = f.make_candidate(other_rec)
        mgr_b = f.make_employee(other_co)
        other_rec.recruitment_managers.add(mgr_b)
        other_iv = f.make_interview(other_cand, interviewers=[mgr_b])
        leaked = f.make_scorecard(
            other_iv, mgr_b, other_co, state=ScorecardState.SUBMITTED,
            feedback="COMPANY_B_SECRET", submitted_at=timezone.now(),
        )
        # Manager of company A over their own interview never sees company B.
        mgr_a = f.make_employee(self.company)
        self.rec.recruitment_managers.add(mgr_a)
        visible = visible_scorecards(viewer=mgr_a, interview=self.interview)
        self.assertNotIn(leaked, visible)
        # KILL-NOTE: drop company_id from the base filter -> cross-tenant -> RED
        # (here the query is scoped to self.interview so the co-key guards the
        # has_finalized_for path; asserts the company filter stays present).
