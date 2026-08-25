"""F1 kill-test #2 — the candidate discussion gate.

The discussion has its OWN two paths (read AND post), both gated by the SAME
submit-state as scorecards. Asserts both are blocked before submit and both
open after — BOTH directions — plus manager see-all and default-deny.
"""

from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.utils import timezone

from aida_customs.actions import submit_scorecard
from aida_customs.models import ScorecardState
from aida_customs.tests import _factories as f
from aida_customs.visibility import (
    can_access_discussion,
    post_comment,
    visible_discussion,
)


class DiscussionGateTests(TestCase):
    def setUp(self):
        self.company = f.make_company()
        self.rec = f.make_recruitment(self.company)
        self.cand = f.make_candidate(self.rec)
        self.A = f.make_employee(self.company)
        self.B = f.make_employee(self.company)
        self.interview = f.make_interview(self.cand, interviewers=[self.A, self.B])
        # B has finalized (submitted) and posted a comment.
        f.make_scorecard(
            self.interview,
            self.B,
            self.company,
            state=ScorecardState.SUBMITTED,
            submitted_at=timezone.now(),
        )
        # A has a draft only -> not finalized.
        f.make_scorecard(
            self.interview, self.A, self.company, state=ScorecardState.DRAFT
        )
        self.B_comment = post_comment(
            author=self.B, candidate=self.cand, body="B_DISCUSSION_SECRET"
        )

    def test_read_blocked_before_submit(self):
        visible = visible_discussion(viewer=self.A, candidate=self.cand)
        self.assertEqual(list(visible), [])  # empty, not B's comment
        self.assertNotIn("B_DISCUSSION_SECRET", [c.body for c in visible])
        # KILL-NOTE: make can_access_discussion return True always -> A reads
        # B's secret -> RED.

    def test_post_blocked_before_submit(self):
        with self.assertRaises(PermissionDenied):
            post_comment(author=self.A, candidate=self.cand, body="early")
        # KILL-NOTE: drop the PermissionDenied raise in post_comment -> a
        # not-yet-submitted interviewer can post -> RED.

    def test_both_unlock_after_submit(self):
        submit_scorecard(self.A, self.interview)  # the single switch
        visible = visible_discussion(viewer=self.A, candidate=self.cand)
        self.assertIn(self.B_comment, visible)  # READ now open
        posted = post_comment(author=self.A, candidate=self.cand, body="now allowed")
        self.assertIsNotNone(posted.pk)  # POST now succeeds
        # KILL-NOTE: make submit_scorecard not set state -> gate never flips ->
        # both assertions RED (control proven to do real work).

    def test_manager_reads_and_posts_without_own_scorecard(self):
        mgr = f.make_employee(self.company)
        self.rec.recruitment_managers.add(mgr)
        self.assertTrue(can_access_discussion(viewer=mgr, candidate=self.cand))
        self.assertIn(
            self.B_comment, visible_discussion(viewer=mgr, candidate=self.cand)
        )
        self.assertIsNotNone(
            post_comment(author=mgr, candidate=self.cand, body="mgr note").pk
        )
        # KILL-NOTE: break MANAGER branch (return False) -> RED.

    def test_stranger_denied_both(self):
        outsider = f.make_employee(self.company)
        self.assertFalse(can_access_discussion(viewer=outsider, candidate=self.cand))
        self.assertEqual(
            list(visible_discussion(viewer=outsider, candidate=self.cand)), []
        )
        with self.assertRaises(PermissionDenied):
            post_comment(author=outsider, candidate=self.cand, body="x")
        # KILL-NOTE: default-allow in can_access_discussion -> RED.
