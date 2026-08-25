"""F1 — thin HTTP layer. Every path routes through ``visibility``; no view
queries the scorecard/comment tables directly. Auth (who) is Horilla's job via
``login_required``; these decide only what a logged-in staff member may see/do.
"""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from aida_customs import visibility
from aida_customs.actions import submit_scorecard
from aida_customs.models import InterviewScorecard


def _employee(request):
    emp = getattr(request.user, "employee_get", None)
    if emp is None:
        raise PermissionDenied("No employee record for this user.")
    return emp


@login_required
@require_http_methods(["POST"])
def submit_scorecard_view(request, scorecard_id):
    viewer = _employee(request)
    card = get_object_or_404(
        InterviewScorecard, pk=scorecard_id, interviewer=viewer
    )
    submit_scorecard(viewer, card.interview)
    return JsonResponse({"status": "submitted", "scorecard_id": card.pk})


@login_required
@require_http_methods(["GET"])
def scorecards_view(request, interview_id):
    from recruitment.models import InterviewSchedule

    interview = get_object_or_404(InterviewSchedule, pk=interview_id)
    cards = visibility.visible_scorecards(viewer=_employee(request), interview=interview)
    return JsonResponse(
        {
            "scorecards": [
                {
                    "id": c.pk,
                    "interviewer": c.interviewer_id,
                    "score": c.score,
                    "feedback": c.feedback,
                    "recommendation": c.recommendation,
                    "state": c.state,
                }
                for c in cards
            ]
        }
    )


@login_required
@require_http_methods(["GET", "POST"])
def discussion_view(request, candidate_id):
    from recruitment.models import Candidate

    candidate = get_object_or_404(Candidate, pk=candidate_id)
    viewer = _employee(request)
    if request.method == "POST":
        parent = None
        parent_id = request.POST.get("parent")
        if parent_id:
            parent = get_object_or_404(
                visibility.CandidateDiscussionComment,
                pk=parent_id,
                candidate=candidate,
            )
        comment = visibility.post_comment(  # raises PermissionDenied -> 403
            author=viewer,
            candidate=candidate,
            body=request.POST.get("body", ""),
            parent=parent,
        )
        return JsonResponse({"status": "posted", "comment_id": comment.pk})
    comments = visibility.visible_discussion(viewer=viewer, candidate=candidate)
    return JsonResponse(
        {
            "comments": [
                {
                    "id": c.pk,
                    "author": c.author_id,
                    "body": c.body,
                    "parent": c.parent_id,
                    "created_at": c.created_at.isoformat(),
                }
                for c in comments
            ]
        }
    )
