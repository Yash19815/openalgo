"""Paper/Live trading mode, Live readiness and masked broker status.

Broker status is read from OpenAlgo's own auth and broker-key configuration;
this module keeps no credentials, starts no login and calls no broker. Only
booleans, the broker id and the key source leave it: never a character or the
length of a token, key or secret.

The live adapter is a stub with no transport. It verifies nothing, so Live
always reports ``LIVE_NOT_READY`` and cannot activate in this release.
"""

from utils.logging import get_logger

logger = get_logger(__name__)

PAPER, LIVE = "PAPER", "LIVE"
MODES = (PAPER, LIVE)

BROKER_STATUS_UNAVAILABLE = "BROKER_STATUS_UNAVAILABLE"
API_MISSING = "API_MISSING"
AUTH_EXPIRED = "AUTH_EXPIRED"
BROKER_UNREACHABLE = "BROKER_UNREACHABLE"
LIVE_NOT_READY = "LIVE_NOT_READY"
MARKET_DATA_UNVERIFIED = "MARKET_DATA_UNVERIFIED"
PROTECTIVE_ORDERS_UNVERIFIED = "PROTECTIVE_ORDERS_UNVERIFIED"
FILL_RECONCILIATION_UNVERIFIED = "FILL_RECONCILIATION_UNVERIFIED"
STATIC_IP_UNVERIFIED = "STATIC_IP_UNVERIFIED"
OPEN_EXPOSURE = "OPEN_EXPOSURE"
ACK_REQUIRED = "ACK_REQUIRED"

READINESS_ORDER = (
    BROKER_STATUS_UNAVAILABLE,
    API_MISSING,
    AUTH_EXPIRED,
    BROKER_UNREACHABLE,
    LIVE_NOT_READY,
    MARKET_DATA_UNVERIFIED,
    PROTECTIVE_ORDERS_UNVERIFIED,
    FILL_RECONCILIATION_UNVERIFIED,
    STATIC_IP_UNVERIFIED,
    OPEN_EXPOSURE,
    ACK_REQUIRED,
)


class LiveAdapterStub:
    """Placeholder for a future broker adapter: no transport, no broker import.

    Every Live prerequisite stays unverified, and ``submit`` refuses.
    """

    name = "LIVE_ADAPTER_STUB"

    def reachable(self):
        return False

    def readiness(self):
        return [
            LIVE_NOT_READY,
            MARKET_DATA_UNVERIFIED,
            PROTECTIVE_ORDERS_UNVERIFIED,
            FILL_RECONCILIATION_UNVERIFIED,
            STATIC_IP_UNVERIFIED,
        ]

    def submit(self, intent):
        from .paper_executor import OrderRefused

        raise OrderRefused([LIVE_NOT_READY])


LIVE_ADAPTER = LiveAdapterStub()

_UNAVAILABLE = {
    "available": False,
    "code": BROKER_STATUS_UNAVAILABLE,
    "broker": None,
    "broker_name": None,
    "auth_token_present": False,
    "feed_token_present": False,
    "revoked": False,
    "session_current": False,
    "api_key_configured": False,
    "api_secret_configured": False,
    "key_source": None,
    "openalgo_api_key_configured": False,
}


def _auth_row(user_id):
    from database.auth_db import Auth

    return Auth.query.filter_by(name=user_id).first()


def read_broker_facts(user_id):
    """Raw facts from OpenAlgo's auth and broker-key stores. May hold secrets.

    Read-only: the stored token is never decrypted, and nothing is written,
    staged or published.
    """
    from database.auth_db import get_api_key
    from utils.broker_keys import broker_title, env_broker, live_broker, resolve

    row = _auth_row(user_id)
    broker = (row.broker if row is not None and row.broker else None) or env_broker()
    revoked = bool(row is not None and row.is_revoked)
    return {
        "broker": broker,
        "broker_name": broker_title(broker) if broker else None,
        "auth": None if row is None else row.auth,
        "feed_token": None if row is None else row.feed_token,
        "revoked": revoked,
        "session_current": bool(
            row is not None and row.auth and not revoked and live_broker() == row.broker
        ),
        "keys": resolve(broker) if broker else None,
        "openalgo_api_key": bool(get_api_key(user_id)),
    }


def _masked(facts):
    """The single masking point: secrets become presence booleans."""
    keys = facts.get("keys")
    return {
        "available": True,
        "code": None,
        "broker": facts.get("broker"),
        "broker_name": facts.get("broker_name"),
        "auth_token_present": bool(facts.get("auth")),
        "feed_token_present": bool(facts.get("feed_token")),
        "revoked": bool(facts.get("revoked")),
        "session_current": bool(facts.get("session_current")),
        "api_key_configured": bool(keys is not None and getattr(keys, "api_key", None)),
        "api_secret_configured": bool(keys is not None and getattr(keys, "api_secret", None)),
        "key_source": getattr(keys, "source", None) if keys is not None else None,
        "openalgo_api_key_configured": bool(facts.get("openalgo_api_key")),
    }


def broker_status(user_id, reader=None):
    """Masked broker status. A failed read returns a generic unavailable status."""
    try:
        return _masked((reader or read_broker_facts)(user_id))
    except Exception as error:
        # The message can echo credentials or connection strings; log the type only.
        logger.warning("NIFTY broker status unavailable: %s", type(error).__name__)
        return dict(_UNAVAILABLE)


def _ordered(codes):
    unique = set(codes)
    return [code for code in READINESS_ORDER if code in unique]


def has_exposure(exposure):
    return bool(exposure.get("positions") or exposure.get("pending_orders"))


def live_readiness(status, exposure, acknowledged):
    """Pure. Refusal codes for a Live request; empty would mean ready (never, here)."""
    codes = []
    if not status.get("available"):
        codes.append(BROKER_STATUS_UNAVAILABLE)
    else:
        if not status.get("api_key_configured") or not status.get("openalgo_api_key_configured"):
            codes.append(API_MISSING)
        if (
            not status.get("auth_token_present")
            or status.get("revoked")
            or not status.get("session_current")
        ):
            codes.append(AUTH_EXPIRED)
    if not status.get("available") or not LIVE_ADAPTER.reachable():
        codes.append(BROKER_UNREACHABLE)
    codes.extend(LIVE_ADAPTER.readiness())
    if has_exposure(exposure):
        codes.append(OPEN_EXPOSURE)
    if acknowledged is not True:
        codes.append(ACK_REQUIRED)
    if LIVE_NOT_READY not in codes:
        codes.append(LIVE_NOT_READY)
    return _ordered(codes)


def mode_refusals(requested, status, exposure, current, acknowledged):
    """Pure. Refusal codes for a mode request evaluated under the user lock."""
    if requested == LIVE:
        return live_readiness(status, exposure, acknowledged)
    if requested == current:
        return []
    return [OPEN_EXPOSURE] if has_exposure(exposure) else []


def mode_overview(store, user_id, reader=None, now=None):
    """Mode, revision, history, Live readiness codes and masked broker status."""
    status = broker_status(user_id, reader)
    exposure = store.open_exposure(user_id, now)
    return {
        **store.trading_mode(user_id),
        "live_available": False,
        "adapter": LIVE_ADAPTER.name,
        "readiness": live_readiness(status, exposure, acknowledged=False),
        "exposure": exposure,
        "broker": status,
    }


def request_mode(
    store, user_id, revision, requested, *, acknowledged, actor, reader=None, now=None
):
    """Decide a mode request once, under the user lock. Returns (mode, codes, changed)."""
    status = broker_status(user_id, reader)
    return store.change_mode(
        user_id,
        revision,
        requested,
        actor=actor,
        evaluate=lambda exposure, current: mode_refusals(
            requested, status, exposure, current, acknowledged
        ),
        snapshot={"broker": status, "adapter": LIVE_ADAPTER.name, "acknowledged": acknowledged},
        now=now,
    )
