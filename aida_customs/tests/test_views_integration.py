"""F1 — witness at the HTTP VIEW layer.

The gate lives in visibility.py, but a future view that queries the models
directly would bypass it and turn no unit test red. These drive the real
Django request path (URL -> view -> gate) so a view that skips the gate fails
here. Asserts the blind rule holds end-to-end for every endpoint.
"""

import json

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from aida_customs.models import ScorecardState
from aida_customs.tests import _factories as f
from aida_customs.visibility import post_comment


class ViewLayerGateTests(TestCase):
    def setUp(self):
        self.company = f.make_company()
        self.rec = f.make_recruitment(self.company)
        self.cand = f.make_candidate(self.rec)
        self.A = f.make_employee(self.company)
        self.B = f.make_employee(self.company)
        self.interview = f.make_interview(self.cand, interviewers=[self.A, self.B])
        self.B_card = f.make_scorecard(
            self.interview,
            self.B,
            self.company,
            state=ScorecardState.SUBMITTED,
            feedback="B_SECRET_FEEDBACK",
            submitted_at=timezone.now(),
        )
        self.A_card = f.make_scorecard(
            self.interview, self.A, self.company, state=ScorecardState.DRAFT
        )
        self.B_comment = post_comment(
            author=self.B, candidate=self.cand, body="B_DISCUSSION_SECRET"
        )
        self.client.force_login(self.A.employee_user_id)

    def _get(self, name, **kw):
        return self.client.get(reverse(f"aida_customs:{name}", kwargs=kw))

    def test_scorecards_view_hides_other_until_submit_through_http(self):
        before = self._get("interview-scorecards", interview_id=self.interview.pk)
        self.assertEqual(before.status_code, 200)
        self.assertNotContains(before, "B_SECRET_FEEDBACK")  # blind via HTTP

        # Submit through the real POST endpoint.
        resp = self.client.post(
            reverse(
                "aida_customs:scorecard-submit", kwargs={"scorecard_id": self.A_card.pk}
            )
        )
        self.assertEqual(resp.status_code, 200)

        after = self._get("interview-scorecards", interview_id=self.interview.pk)
        self.assertContains(after, "B_SECRET_FEEDBACK")  # unlocked via HTTP
        # KILL-NOTE: make scorecards_view query InterviewScorecard directly
        # (bypassing visible_scorecards) -> B leaks before submit -> RED.

    def test_discussion_get_blind_then_open_through_http(self):
        before = self._get("candidate-discussion", candidate_id=self.cand.pk)
        self.assertEqual(before.status_code, 200)
        self.assertNotContains(before, "B_DISCUSSION_SECRET")

        self.client.post(
            reverse(
                "aida_customs:scorecard-submit", kwargs={"scorecard_id": self.A_card.pk}
            )
        )
        after = self._get("candidate-discussion", candidate_id=self.cand.pk)
        self.assertContains(after, "B_DISCUSSION_SECRET")
        # KILL-NOTE: make discussion_view read the comment table directly -> the
        # secret leaks before submit -> RED.

    def test_discussion_post_403_until_submit_through_http(self):
        url = reverse(
            "aida_customs:candidate-discussion", kwargs={"candidate_id": self.cand.pk}
        )
        blocked = self.client.post(url, {"body": "A posts early"})
        self.assertEqual(blocked.status_code, 403)  # PermissionDenied -> 403
        self.assertEqual(self.cand.discussion.filter(author=self.A).count(), 0)

        self.client.post(
            reverse(
                "aida_customs:scorecard-submit", kwargs={"scorecard_id": self.A_card.pk}
            )
        )
        allowed = self.client.post(url, {"body": "A posts after submit"})
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(self.cand.discussion.filter(author=self.A).count(), 1)
        # KILL-NOTE: make discussion_view POST call the model create directly
        # (bypassing post_comment) -> the early post succeeds (200, row created)
        # -> RED.
