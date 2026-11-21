"""Single, shared Owner identity resolution and promotion.

Every path that may grant, keep or transfer the ``OWNER`` role goes through this
module, so signup, request-path synchronisation, deployment reconciliation and
the one-time bootstrap cannot diverge:

* :func:`evaluate` — pure decision function (no I/O, no writes).
* :func:`reconcile_owner` — performs an atomic, locking promotion/transfer.
* :func:`normalize_email` — the one comparison convention (trim + lowercase).

Security invariants (all enforced here, none by the caller):

* only a **verified Clerk primary email** qualifies — never a secondary address,
  never an unverified address, never an address supplied by the client, never
  Clerk metadata, never a cached local value;
* an inactive account is never promoted;
* the previous Owner becomes ``ADMIN`` and is otherwise untouched (no deletion,
  no deactivation, no ``clerk_id`` change);
* exactly one Owner exists after any successful call, guaranteed by the partial
  unique index ``uq_users_single_owner`` plus a transaction-scoped advisory lock
  on PostgreSQL;
* ambiguity or an identity-service failure means *no change*, never an
  unverified transfer.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from enum import Enum

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.auth import _verified_primary_email
from app.enums.enums import Role
from app.models.user import User

logger = logging.getLogger(__name__)

# Stable key for the transaction-level advisory lock, distinct from the ticket
# assignment and demo-seed keys so unrelated transactions never contend.
OWNER_RECONCILE_LOCK_KEY = 20261122


def normalize_email(value: str | None) -> str | None:
    """The single email comparison convention: trim, lowercase, or ``None``."""
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None


class OwnerAction(str, Enum):
    """What a reconciliation call decided (or would decide)."""

    NO_CONFIG = "no_config"
    """No OWNER_EMAIL configured; ownership is left exactly as it is."""

    ALREADY_OWNER = "already_owner"
    """The designated account already holds OWNER; nothing to do."""

    PROMOTED = "promoted"
    """A new Owner was promoted (there was no previous Owner)."""

    TRANSFERRED = "transferred"
    """Ownership moved; the previous Owner is now ADMIN."""

    TARGET_MISSING = "target_missing"
    """No local account matches the configured address yet; no change."""

    TARGET_INACTIVE = "target_inactive"
    """The designated account is inactive; no change."""

    NOT_VERIFIED = "not_verified"
    """The identity has no verified primary email matching the configuration."""

    IDENTITY_UNAVAILABLE = "identity_unavailable"
    """Clerk could not be reached; ownership is preserved unchanged."""


@dataclass(frozen=True)
class OwnerDecision:
    """The outcome of evaluating a candidate, plus the values it acted on."""

    action: OwnerAction
    owner_email: str | None = None
    target_user_id: uuid.UUID | None = None
    previous_owner_id: uuid.UUID | None = None
    verified_email: str | None = None

    @property
    def changed(self) -> bool:
        return self.action in (OwnerAction.PROMOTED, OwnerAction.TRANSFERRED)


class OwnerIdentityError(RuntimeError):
    """A caller-facing, sanitized reason reconciliation could not complete.

    The message never contains an email address, token or Clerk secret.
    """


async def _lock_ownership(session: AsyncSession) -> None:
    """Serialise ownership changes for this transaction on PostgreSQL.

    A transaction-scoped advisory lock is released automatically on commit or
    rollback. SQLite serialises writers itself, so tests need no extra lock.
    """
    bind = session.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        await session.exec(
            text("SELECT pg_advisory_xact_lock(:key)"),
            params={"key": OWNER_RECONCILE_LOCK_KEY},
        )


async def _current_owner(session: AsyncSession) -> User | None:
    return (await session.exec(select(User).where(User.role == Role.OWNER))).first()


async def _verified_email_for(clerk_user) -> str | None:
    """Normalized verified primary email from a resolved Clerk user object."""
    return normalize_email(_verified_primary_email(clerk_user))


async def evaluate(
    session: AsyncSession,
    *,
    clerk,
    candidate: User | None,
    configured_email: str | None,
    clerk_user=None,
) -> OwnerDecision:
    """Decide what should happen to ``candidate`` without changing anything.

    ``candidate`` is the local account already matched to the authenticated
    identity (by Clerk id or verified email). ``clerk_user`` may be supplied when
    the caller already fetched it; otherwise it is fetched here so the *Clerk*
    record is always the source of the email, never the local row.

    The function performs reads only. It raises :class:`OwnerIdentityError` only
    for a genuine infrastructure failure that the caller must surface; every
    other outcome is a :class:`OwnerDecision` with ``changed == False``.
    """
    email = normalize_email(configured_email)
    if email is None:
        return OwnerDecision(OwnerAction.NO_CONFIG)
    if candidate is None:
        return OwnerDecision(OwnerAction.TARGET_MISSING, owner_email=email)

    # The account must be active before it can be considered at all.
    if not candidate.is_active:
        return OwnerDecision(
            OwnerAction.TARGET_INACTIVE,
            owner_email=email,
            target_user_id=candidate.id,
        )

    # Resolve the trusted Clerk identity. The local email is never trusted.
    if clerk_user is None:
        if not candidate.clerk_id:
            return OwnerDecision(
                OwnerAction.NOT_VERIFIED,
                owner_email=email,
                target_user_id=candidate.id,
            )
        try:
            clerk_user = await clerk.users.get_async(user_id=candidate.clerk_id)
        except Exception as exc:  # noqa: BLE001 - surfaced as a safe decision
            logger.warning(
                "Owner identity verification unavailable (%s); ownership preserved",
                type(exc).__name__,
            )
            return OwnerDecision(
                OwnerAction.IDENTITY_UNAVAILABLE,
                owner_email=email,
                target_user_id=candidate.id,
            )

    verified_email = await _verified_email_for(clerk_user)
    if verified_email != email:
        return OwnerDecision(
            OwnerAction.NOT_VERIFIED,
            owner_email=email,
            target_user_id=candidate.id,
            verified_email=verified_email,
        )

    if candidate.role == Role.OWNER:
        return OwnerDecision(
            OwnerAction.ALREADY_OWNER,
            owner_email=email,
            target_user_id=candidate.id,
            verified_email=verified_email,
        )

    current = await _current_owner(session)
    action = OwnerAction.PROMOTED if current is None else OwnerAction.TRANSFERRED
    return OwnerDecision(
        action,
        owner_email=email,
        target_user_id=candidate.id,
        previous_owner_id=current.id if current is not None else None,
        verified_email=verified_email,
    )


async def reconcile_owner(
    session: AsyncSession,
    *,
    clerk,
    candidate: User | None,
    configured_email: str | None,
    clerk_user=None,
    commit: bool = True,
) -> OwnerDecision:
    """Apply :func:`evaluate` atomically.

    On PostgreSQL the whole operation runs under a transaction-scoped advisory
    lock. The transfer is ordered so the unique index is never violated: the
    previous Owner is demoted to ``ADMIN`` and flushed *before* the new Owner is
    promoted, inside the same transaction. A failure rolls everything back.
    """
    await _lock_ownership(session)

    decision = await evaluate(
        session,
        clerk=clerk,
        candidate=candidate,
        configured_email=configured_email,
        clerk_user=clerk_user,
    )
    if not decision.changed or decision.target_user_id is None:
        return decision

    target = await session.get(User, decision.target_user_id, with_for_update=True)
    if target is None:  # pragma: no cover - row disappeared mid-transaction
        return OwnerDecision(
            OwnerAction.TARGET_MISSING, owner_email=decision.owner_email
        )

    previous = (
        await session.get(User, decision.previous_owner_id, with_for_update=True)
        if decision.previous_owner_id is not None
        else None
    )

    try:
        # Demote first so the partial unique index never sees two Owners.
        if previous is not None and previous.id != target.id:
            previous.role = Role.ADMIN
            session.add(previous)
            await session.flush()

        target.role = Role.OWNER
        session.add(target)
        await session.flush()

        if commit:
            await session.commit()
        else:  # caller owns the transaction boundary
            await session.flush()
    except IntegrityError:
        await session.rollback()
        raise OwnerIdentityError(
            "Ownership could not be reconciled without violating the single-Owner "
            "constraint; no change was applied."
        ) from None
    except Exception:
        await session.rollback()
        raise

    logger.info(
        "Owner identity reconciled: %s",
        decision.action.value,
    )
    return decision


async def find_candidate_by_email(
    session: AsyncSession, configured_email: str | None
) -> User | None:
    """The local account whose normalized email matches the configuration."""
    email = normalize_email(configured_email)
    if email is None:
        return None
    return (await session.exec(select(User).where(User.email == email))).first()
