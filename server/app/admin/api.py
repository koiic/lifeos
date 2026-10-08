"""admin: HTTP layer: request and response handling only (plan 4.2).

T08 builds the AUTH-8 recovery invite here; the rest of the admin console is T44. Every admin
endpoint needs a signed-in session whose account has the `admin` role (spec 7.2 `users.role`).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.auth.api import Account, Client, Now, SessionContext, no_store, problems, require_session
from app.auth.schemas import RecoveryInvite

router = APIRouter(prefix="/api/v1/admin", tags=["admin"], dependencies=[Depends(no_store)])


async def require_admin(
    session: Annotated[SessionContext, Depends(require_session)], account: Account
) -> SessionContext:
    """403 unless the signed-in account is an admin."""
    if await account.role(session) != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admins only.")
    return session


Admin = Annotated[SessionContext, Depends(require_admin)]


@router.post(
    "/users/{user_id}/recovery-invite",
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"description": "Not signed in."},
        403: {"description": "Not an admin, or no recent authentication (CR-020)."},
        404: {"description": "No such account."},
        503: {"description": "Admin changes are not configured (CR-022)."},
    },
)
async def issue_recovery_invite(
    user_id: uuid.UUID, admin: Admin, account: Account, now: Now, client: Client, response: Response
) -> RecoveryInvite:
    """AUTH-8: a single-use, 24-hour link to add a passkey to her account. Issuing it revokes all
    her sessions, queues a security notice to her devices and is audited."""
    with problems():
        token, expires_at = await account.issue_recovery_invite(admin, user_id, now, client)
    return RecoveryInvite(token=token, link=f"/recover?token={token}", expires_at=expires_at)
