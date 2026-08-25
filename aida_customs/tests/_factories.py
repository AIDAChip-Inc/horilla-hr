"""Minimal object graph for F1 gate tests.

Builds real Horilla rows (Company, Recruitment, Candidate, InterviewSchedule,
Employee/HorillaUser) so the visibility gate is exercised against production
relations, not mocks.
"""

from datetime import date, time

from aida_customs.models import InterviewScorecard, Recommendation, ScorecardState
from base.models import Company, Department, JobPosition
from employee.models import Employee, EmployeeWorkInformation
from horilla_auth.models import HorillaUser
from recruitment.models import Candidate, InterviewSchedule, Recruitment

_counter = {"n": 0}


def _uniq():
    _counter["n"] += 1
    return _counter["n"]


def make_company(name="AIDA"):
    return Company.objects.create(
        company=f"{name}-{_uniq()}",
        address="1 St",
        country="US",
        state="CA",
        city="SF",
        zip="94000",
    )


def make_employee(company=None, is_superuser=False, email=None):
    n = _uniq()
    email = email or f"emp{n}@aidachip.com"
    user = HorillaUser.objects.create_user(
        username=f"user{n}", email=email, password="x"
    )
    if is_superuser:
        user.is_superuser = True
        user.save(update_fields=["is_superuser"])
    employee = Employee.objects.create(
        employee_user_id=user,
        employee_first_name=f"Emp{n}",
        employee_last_name="T",
        email=email,
        phone=f"+1000000{n:04d}",
    )
    # Give the employee a work-info company so get_company() resolves the tenant
    # co-key (the visibility gate keys on the VIEWER's company, not the object).
    # Horilla may auto-create a work-info row, so update the existing one.
    if company is not None:
        wi = EmployeeWorkInformation.objects.filter(employee_id=employee).first()
        if wi is None:
            wi = EmployeeWorkInformation(employee_id=employee)
        wi.company_id = company
        wi.save()
        # Re-fetch so the instance's cached reverse work-info relation reflects
        # the company we just set (get_company() reads self.employee_work_info).
        employee = Employee.objects.get(pk=employee.pk)
    return employee


def make_job_position(company):
    n = _uniq()
    dept = Department.objects.create(department=f"Dept{n}")
    dept.company_id.add(company)
    jp = JobPosition.objects.create(job_position=f"JP{n}", department_id=dept)
    jp.company_id.add(company)
    return jp


def make_recruitment(company, managers=()):
    jp = make_job_position(company)
    rec = Recruitment.objects.create(
        title=f"Role-{_uniq()}", company_id=company, job_position_id=jp
    )
    rec.open_positions.add(jp)
    rec._job_position = jp  # convenience for candidate creation
    for m in managers:
        rec.recruitment_managers.add(m)
    return rec


def make_candidate(recruitment):
    n = _uniq()
    return Candidate.objects.create(
        name=f"Cand{n}",
        email=f"cand{n}@example.com",
        recruitment_id=recruitment,
        job_position_id=getattr(recruitment, "_job_position", None)
        or recruitment.job_position_id,
    )


def make_interview(candidate, interviewers=()):
    iv = InterviewSchedule.objects.create(
        candidate_id=candidate,
        interview_date=date(2026, 9, 1),
        interview_time=time(10, 0),
    )
    for i in interviewers:
        iv.employee_id.add(i)
    return iv


def make_scorecard(
    interview,
    interviewer,
    company,
    state=ScorecardState.DRAFT,
    feedback="fb",
    score=3,
    submitted_at=None,
):
    return InterviewScorecard.objects.create(
        interview=interview,
        interviewer=interviewer,
        company_id=company,
        state=state,
        feedback=feedback,
        score=score,
        recommendation=Recommendation.YES,
        submitted_at=submitted_at,
    )
