"""notify: HTTP layer: request and response handling only (plan 4.2).

Spec 9.2 push rows: the VAPID public key, saving and removing a subscription, and the test push
(ONB-3). Every endpoint needs a signed-in session.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.auth.api import Now, SessionContext, no_store, require_session
from app.notify.schemas import SubscriptionIn, SubscriptionRef, TestPushResult, VapidPublicKey
from app.notify.service import NotifyError, NotifyService

router = APIRouter(prefix="/api/v1/push", tags=["push"], dependencies=[Depends(no_store)])

SignedIn = Annotated[SessionContext, Depends(require_session)]
SIGNED_IN: dict[int | str, dict[str, Any]] = {
    401: {"description": "Not signed in, or the session has ended."},
    403: {"description": "Account not activated (CR-014)."},
    429: {"description": "More than 300 requests in a minute on this session (9.1)."},
}


def get_service(request: Request) -> NotifyService:
    service: NotifyService = request.app.state.notify
    return service


Service = Annotated[NotifyService, Depends(get_service)]


@contextmanager
def problems() -> Iterator[None]:
    try:
        yield
    except NotifyError as error:
        raise HTTPException(error.status, error.detail) from None


@router.get("/vapid-public-key", responses=SIGNED_IN)
async def vapid_public_key(_session: SignedIn, service: Service) -> VapidPublicKey:
    """The browser's `applicationServerKey` for `pushManager.subscribe`."""
    return VapidPublicKey(public_key=service.vapid_public_key)


@router.post(
    "/subscriptions",
    status_code=status.HTTP_201_CREATED,
    responses=SIGNED_IN
    | {
        409: {"description": "The endpoint belongs to another account."},
        422: {"description": "Not a push service endpoint, or malformed keys."},
    },
)
async def save_subscription(
    body: SubscriptionIn, session: SignedIn, service: Service, now: Now
) -> Response:
    """Save this device's subscription (again: the app re-registers it on every start, 10.5)."""
    with problems():
        await service.save_subscription(session.user_id, session.session_id, body, now)
    response = Response(status_code=status.HTTP_201_CREATED)
    no_store(response)
    return response


@router.delete(
    "/subscriptions",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=SIGNED_IN | {404: {"description": "Not found."}},
)
async def remove_subscription(
    body: SubscriptionRef, session: SignedIn, service: Service
) -> Response:
    with problems():
        await service.remove_subscription(session.user_id, body.endpoint)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    no_store(response)
    return response


@router.post(
    "/test",
    responses=SIGNED_IN | {409: {"description": "No device is set up for notifications."}},
)
async def send_test_push(session: SignedIn, service: Service, now: Now) -> TestPushResult:
    """ONB-3, 10.7 `test`: "Notifications are on" to every device she has turned on."""
    with problems():
        delivered = await service.send_test(session.user_id, now)
    return TestPushResult(delivered=delivered)
