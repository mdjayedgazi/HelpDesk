"""One-time Owner bootstrap.

Usage, from the ``backend/`` directory with the project environment active:

    uv run python -m app.commands.bootstrap_owner

This promotes the single existing local account whose *verified Clerk primary
email* matches the configured ``OWNER_EMAIL`` (or the deprecated
``INITIAL_ADMIN_EMAIL`` fallback) to the permanent ``OWNER`` role. It is a
deliberate, explicit setup step, still useful for initial provisioning and for
operations where automatic reconciliation has not yet run:

* it never runs automatically on application startup,
* it never creates a user (all signups are CUSTOMER),
* it never promotes an arbitrary first signup,
* it refuses to run once an Owner already exists, so it cannot overwrite or
  transfer ownership,
* it re-verifies the identity against the Clerk Backend API before promoting.

After a successful run the Owner role is stored in PostgreSQL. The
``OWNER_EMAIL`` setting stays authoritative: it is what the request path uses to
recognise the Owner automatically and to move ownership when the address changes.
Removing it disables automatic recognition but does not change a stored role.
"""

from __future__ import annotations

import asyncio
import sys

from sqlmodel import select

from app.core.auth import _verified_primary_email, clerk_client
from app.core.config import settings
from app.core.database import async_session
from app.enums.enums import Role
from app.models.user import User


class BootstrapError(RuntimeError):
    """A safe, user-facing reason ownership could not be established.

    The message never contains secrets; the configured email address is not
    echoed back except where it is already public to the operator.
    """


async def promote_owner(session, *, clerk, configured_email: str | None) -> User:
    """Transactionally promote the configured identity to ``OWNER``.

    Returns the promoted user. Raises :class:`BootstrapError` with a safe,
    actionable message on any refusal. Never creates a user and never overwrites
    an existing Owner.
    """
    if not configured_email:
        raise BootstrapError(
            "OWNER_EMAIL is not set. Configure it in the backend environment, then "
            "sign in once with that account before running the bootstrap."
        )

    # 1. Refuse to run when ownership is already established.
    existing_owner = (
        await session.exec(select(User).where(User.role == Role.OWNER))
    ).first()
    if existing_owner is not None:
        raise BootstrapError(
            "An Owner already exists. Ownership is already established and will "
            "not be overwritten by this command."
        )

    # 2. Find the matching local account (must already exist).
    target = (
        await session.exec(select(User).where(User.email == configured_email))
    ).first()
    if target is None:
        raise BootstrapError(
            "No local account matches the configured bootstrap email. Sign in "
            "to HelpDesk once with that account so it is provisioned, then retry."
        )

    # 3. The account must already be linked to a Clerk identity.
    if not target.clerk_id:
        raise BootstrapError(
            "The matching account is not linked to a Clerk identity yet. Sign in "
            "to HelpDesk with that account, then retry."
        )

    # 4. Eligibility: the account must be active.
    if not target.is_active:
        raise BootstrapError(
            "The matching account is inactive. Reactivate it before bootstrapping."
        )

    # 5. Re-verify the identity's verified primary email against Clerk.
    try:
        clerk_user = await clerk.users.get_async(user_id=target.clerk_id)
    except Exception as exc:  # noqa: BLE001 - surfaced as a safe message
        raise BootstrapError(
            "Could not verify the identity with Clerk "
            f"({type(exc).__name__}). Check connectivity and credentials, then retry."
        ) from None

    if _verified_primary_email(clerk_user) != configured_email:
        raise BootstrapError(
            "The Clerk identity's verified primary email does not match the "
            "configured bootstrap email. Refusing to promote."
        )

    # 6. Promote through the shared owner-identity service so the bootstrap and
    #    the automatic request-path recognition can never use different rules.
    #    The service re-verifies the Clerk identity, applies the same
    #    eligibility checks and relies on the partial unique index.
    from app.services.owner_identity import OwnerIdentityError, reconcile_owner

    try:
        decision = await reconcile_owner(
            session,
            clerk=clerk,
            candidate=target,
            configured_email=configured_email,
            clerk_user=clerk_user,
        )
    except OwnerIdentityError as exc:
        raise BootstrapError(str(exc)) from None

    if not decision.changed and decision.action.value != "already_owner":
        raise BootstrapError(
            "The identity did not qualify for ownership; no changes were applied."
        )

    await session.refresh(target)
    return target


async def _main() -> int:
    configured_email = settings.owner_email
    try:
        async with async_session() as session:
            user = await promote_owner(
                session,
                clerk=clerk_client,
                configured_email=configured_email,
            )
    except BootstrapError as exc:
        print(f"Owner bootstrap failed: {exc}", file=sys.stderr)
        return 1

    # Never print the email address or any credential.
    print(
        "Owner bootstrap succeeded: "
        f"{user.username} ({user.id}) is now the OWNER. "
        "OWNER_EMAIL remains authoritative for automatic recognition."
    )
    return 0


def main() -> int:
    """Synchronous entry point for ``python -m app.commands.bootstrap_owner``."""
    return asyncio.run(_main())


if __name__ == "__main__":
    raise SystemExit(main())
