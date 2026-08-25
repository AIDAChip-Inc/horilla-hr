"""aida_customs routes (mounted at /aida/ by AidaCustomsConfig.ready())."""

from django.urls import path

from aida_customs import views

app_name = "aida_customs"

urlpatterns = [
    path(
        "scorecard/<int:scorecard_id>/submit/",
        views.submit_scorecard_view,
        name="scorecard-submit",
    ),
    path(
        "interview/<int:interview_id>/scorecards/",
        views.scorecards_view,
        name="interview-scorecards",
    ),
    path(
        "candidate/<int:candidate_id>/discussion/",
        views.discussion_view,
        name="candidate-discussion",
    ),
]
