"""Deployment-time Owner reconciliation.

Run after migrations during release, or on demand by an operator:

    uv run python -m app.commands.reconcile_owner

It reads ``OWNER_EMAIL`` (falling back to the deprecated
``INITIAL_ADMIN_EMAIL``), finds the linked local account whose **verified Clerk
primary email** matches it, and atomically makes that account the single Owner.
The previous Owner, if any, becomes ``ADMIN`` and is otherwise untouched.

Design rules (all deliberate):

* **Never fatal to availability.** If the designated account has not registered
  yet, or Clerk is unreachable, the command exits ``0`` with a clear status and
  leaves ownership exactly as it was. A deploy must not fail because a person
  has not signed up.
* **Idempotent.** Running it repeatedly is a no-op once ownership matches.
* **No account creation.** It never creates a user and never writes a
  ``clerk_id``; the account must have signed in normally at least once.
* **One algorithm.** It calls the same ``app.services.owner_identity`` service
  used by the request path and the bootstrap command.

Exit codes: ``0`` reconciled / nothing to do / not-yet-possible (all safe),
``1`` an unexpected database failure, ``2`` refused configuration.
"""

from __future__ import annotations

import asyncio
import json
import sys

from app.core.auth import clerk_client
from app.core.config import settings
from app.core.database import async_session
from app.services.owner_identity import (
    OwnerAction,
    OwnerIdentityError,
    find_candidate_by_email,
    reconcile_owner,
)


async def _run(json_output: bool) -> int:
    configured = settings.owner_email
    if configured is None:
        print(
            "Owner reconciliation skipped: OWNER_EMAIL is not configured.",
            file=sys.stderr,
        )
        return 2

    try:
        async with async_session() as session:
            candidate = await find_candidate_by_email(session, configured)
            if candidate is None:
                # Not registered yet: preserve ownership and succeed so the
                # deployment proceeds. The next sign-in will recognise them.
                decision_payload = {
                    "status": OwnerAction.TARGET_MISSING.value,
                    "changed": False,
                    "note": "designated account has not signed in yet",
                }
                if json_output:
                    print(json.dumps(decision_payload))
                else:
                    print(
                        "Owner reconciliation: designated account has not signed "
                        "in yet; existing ownership preserved."
                    )
                return 0

            decision = await reconcile_owner(
                session,
                clerk=clerk_client,
                candidate=candidate,
                configured_email=configured,
            )
    except OwnerIdentityError as exc:
        # A constraint/transaction problem is a real failure worth surfacing.
        print(f"Owner reconciliation failed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - never fail the deploy
        print(
            "Owner reconciliation could not complete "
            f"({type(exc).__name__}); existing ownership preserved.",
            file=sys.stderr,
        )
        return 0

    payload = {
        "status": decision.action.value,
        "changed": decision.changed,
    }
    if json_output:
        print(json.dumps(payload))
    else:
        print(
            f"Owner reconciliation: {decision.action.value} (changed={decision.changed})."
        )
    return 0


def main() -> int:
    json_output = "--json" in sys.argv[1:]
    return asyncio.run(_run(json_output))


if __name__ == "__main__":
    raise SystemExit(main())
