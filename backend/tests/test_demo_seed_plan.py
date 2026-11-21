"""Fast, database-free coverage for the demo seed plan and CLI surface.

The heavy end-to-end assertions live in ``test_demo_seed_postgres.py`` (opt-in,
disposable PostgreSQL). This module runs everywhere and guards the behaviours
that changed in the demo-dataset pass:

* the dataset plan supports exactly the documented sizes and honours the
  schema's single-Owner rule;
* the dry-run report is complete, internally consistent, and performs no I/O;
* generated timestamps are anchored to the run time, so the 14-day analytics
  window is populated, and are causally ordered;
* active work is never assigned to an inactive agent;
* the CLI exposes ``--size`` and ``--dry-run`` and refuses unsupported sizes.

Nothing here touches a database or the network.
"""

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.commands import seed_demo_data as sd
from app.enums.enums import Role, TicketPriority, TicketStatus


@pytest.fixture(autouse=True)
def _reset_plan():
    """Each test starts from the default 100-user plan and restores it after."""
    sd.use_plan(sd.plan_for(100))
    yield
    sd.use_plan(sd.plan_for(100))


# --------------------------------------------------------------------------- #
# Plan
# --------------------------------------------------------------------------- #


def test_plan_sizes_are_exactly_50_and_100():
    assert sd.plan_for(100).users_total == 100
    assert sd.plan_for(50).users_total == 50
    for bad in (0, 42, 99, 101):
        with pytest.raises(sd.SeedRefused):
            sd.plan_for(bad)


@pytest.mark.parametrize("size", [50, 100])
def test_plan_has_exactly_one_owner_worth_of_roles(size):
    plan = sd.plan_for(size)
    # +1 for the preserved Owner, which is never part of demo_users().
    assert plan.users_total - plan.demo_users == 1


@pytest.mark.parametrize(
    ("size", "admins", "agents", "customers"),
    [(100, 8, 20, 71), (50, 4, 10, 35)],
)
def test_role_split_matches_the_documented_distribution(
    size, admins, agents, customers
):
    plan = sd.plan_for(size)
    assert (plan.admins, plan.agents, plan.customers) == (admins, agents, customers)


def test_apportionment_is_exact():
    counts = sd._split_counts(300, sd._STATUS_WEIGHTS)
    assert sum(counts.values()) == 300
    assert counts[TicketStatus.OPEN] == 60
    assert counts[TicketStatus.IN_PROGRESS] == 60
    assert counts[TicketStatus.WAITING_ON_CUSTOMER] == 60
    assert counts[TicketStatus.RESOLVED] == 90
    assert counts[TicketStatus.CLOSED] == 30

    priorities = sd._split_counts(300, sd._PRIORITY_WEIGHTS)
    assert sum(priorities.values()) == 300
    assert priorities[TicketPriority.LOW] == 45
    assert priorities[TicketPriority.NORMAL] == 135
    assert priorities[TicketPriority.HIGH] == 90
    assert priorities[TicketPriority.URGENT] == 30


# --------------------------------------------------------------------------- #
# Generated data shape
# --------------------------------------------------------------------------- #


def test_demo_users_are_reserved_and_unique():
    users = sd.demo_users()
    assert len(users) == 99
    assert len({u.username for u in users}) == len(users)
    assert len({u.email for u in users}) == len(users)
    assert all(u.email.endswith("@example.test") for u in users)
    # No synthetic user is ever the Owner.
    assert all(u.role != Role.OWNER for u in users)


def test_time_anchor_is_the_run_time_not_a_frozen_date():
    plan = sd.plan_for(100)
    delta = abs((plan.anchor - datetime.now(UTC)).total_seconds())
    assert delta < 3600


@pytest.mark.parametrize("size", [50, 100])
def test_timeline_populates_the_14_day_window(size):
    sd.use_plan(sd.plan_for(size))
    tickets = sd.ticket_specs(sd.demo_users())
    recent = [t for t in tickets if t["created_at"] >= -14 * sd.MINUTES_PER_DAY]
    assert recent, "the analytics window would be empty"
    # Resolutions are spread across the window as well, not clustered on one day.
    resolved_days = {
        t["created_at"] // sd.MINUTES_PER_DAY
        for t in tickets
        if t["resolved_offset"] is not None
        and t["created_at"] + t["resolved_offset"] >= -14 * sd.MINUTES_PER_DAY
    }
    assert len(resolved_days) > 3


def test_lifecycle_timestamps_are_causal_and_never_in_the_future():
    sd.use_plan(sd.plan_for(100))
    for t in sd.ticket_specs(sd.demo_users()):
        assert t["created_at"] <= t["updated_at"] <= 0
        if t["resolved_offset"] is not None:
            assert t["resolved_offset"] > 0
            assert t["created_at"] + t["resolved_offset"] <= 0


def test_comments_never_precede_their_ticket():
    sd.use_plan(sd.plan_for(100))
    users = sd.demo_users()
    tickets = sd.ticket_specs(users)
    created = {t["key"]: t["created_at"] for t in tickets}
    for comment in sd.comment_specs(users, tickets):
        assert comment["at"] >= created[comment["ticket_key"]]


def test_only_staff_author_internal_notes():
    sd.use_plan(sd.plan_for(100))
    users = sd.demo_users()
    staff = {u.key for u in users if u.role in (Role.AGENT, Role.ADMIN)}
    internal = [
        c for c in sd.comment_specs(users, sd.ticket_specs(users)) if c["internal"]
    ]
    assert internal
    assert all(c["author_key"] in staff for c in internal)


def test_active_work_is_never_assigned_to_an_inactive_agent():
    sd.use_plan(sd.plan_for(100))
    users = sd.demo_users()
    inactive = {u.key for u in users if not u.is_active}
    for t in sd.ticket_specs(users):
        if t["status"] in (
            TicketStatus.OPEN,
            TicketStatus.IN_PROGRESS,
            TicketStatus.WAITING_ON_CUSTOMER,
        ):
            assert t["agent_key"] not in inactive


def test_urgent_work_is_spread_across_statuses():
    sd.use_plan(sd.plan_for(100))
    urgent = [
        t
        for t in sd.ticket_specs(sd.demo_users())
        if t["priority"] == TicketPriority.URGENT
    ]
    statuses = {t["status"] for t in urgent}
    assert len(statuses) >= 3  # not all resolved, not all open
    assert any(
        t["status"] in (TicketStatus.OPEN, TicketStatus.IN_PROGRESS) for t in urgent
    )


# --------------------------------------------------------------------------- #
# Dry run
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("size", [50, 100])
def test_dry_run_report_is_consistent(size):
    plan = sd.use_plan(sd.plan_for(size))
    report = sd.dry_run_report(plan)
    expected = report["expected"]

    assert report["dry_run"] is True
    assert expected["size"] == size
    assert expected["users_total"] == size
    assert expected["owners"] == 1
    assert (
        expected["users_total"]
        == 1 + expected["admins"] + expected["agents"] + expected["customers"]
    )
    assert expected["tickets"] == {50: 150, 100: 300}[size]
    assert sum(expected["tickets_by_status"].values()) == expected["tickets"]
    assert sum(expected["tickets_by_priority"].values()) == expected["tickets"]

    derived = report["derived"]
    assert 12 <= derived["unassigned_active_pct"] <= 22
    assert derived["created_in_last_14_days"] > 0
    assert derived["aging_over_7_days"] > 0
    assert derived["unassigned_over_24h"] > 0


def test_dry_run_output_is_json_serialisable():
    sd.use_plan(sd.plan_for(100))
    payload = json.dumps(sd.dry_run_report(sd.active_plan()))
    assert '"dry_run": true' in payload


def test_dry_run_writes_nothing(monkeypatch):
    def _boom(*_args, **_kwargs):
        raise AssertionError("dry-run must not touch the database")

    monkeypatch.setattr(sd, "async_session", _boom)
    sd.use_plan(sd.plan_for(100))
    assert sd.dry_run_report(sd.active_plan())["dry_run"] is True


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def test_cli_dry_run_exits_zero_without_database(monkeypatch, capsys):
    monkeypatch.delenv(sd.CONFIRM_ENV, raising=False)
    code = asyncio.run(sd._main(["--dry-run", "--size", "100"]))
    assert code == 0
    printed = capsys.readouterr().out
    assert "DRY RUN" in printed
    assert "300" in printed


def test_cli_rejects_unsupported_size():
    # argparse rejects a value outside the choices before our code runs.
    with pytest.raises(SystemExit) as excinfo:
        asyncio.run(sd._main(["--dry-run", "--size", "42"]))
    assert excinfo.value.code == 2


def test_cli_real_run_requires_the_confirm_token(monkeypatch, capsys):
    monkeypatch.delenv(sd.CONFIRM_ENV, raising=False)
    code = asyncio.run(sd._main(["--size", "100"]))
    assert code == 2
    assert "confirmation is required" in capsys.readouterr().err.lower()


def test_cli_refuses_declared_production(monkeypatch, capsys):
    monkeypatch.setenv(sd.CONFIRM_ENV, sd.EXPECTED_TOKEN)
    monkeypatch.setenv("HELPDESK_ENVIRONMENT", "production")
    monkeypatch.delenv(sd.PRODUCTION_OVERRIDE_ENV, raising=False)
    code = asyncio.run(sd._main(["--size", "100"]))
    assert code == 2
    assert "production" in capsys.readouterr().err.lower()


def test_production_refusal_requires_the_exact_override_phrase():
    prod = {"HELPDESK_ENVIRONMENT": "production"}
    with pytest.raises(sd.SeedRefused):
        sd.assert_not_production(prod)
    with pytest.raises(sd.SeedRefused):
        sd.assert_not_production({**prod, sd.PRODUCTION_OVERRIDE_ENV: "yes please"})
    # The exact phrase is accepted, and no other guard is skipped by it.
    sd.assert_not_production(
        {**prod, sd.PRODUCTION_OVERRIDE_ENV: sd.PRODUCTION_OVERRIDE_VALUE}
    )
    # Non-production environments need no override.
    sd.assert_not_production({"HELPDESK_ENVIRONMENT": "development"})


def test_guard_rejects_uploads_outside_tmp():
    repo_dir = str(Path(__file__).resolve().parent)
    with pytest.raises(sd.SeedRefused):
        sd.assert_safe_upload_dir(repo_dir)
