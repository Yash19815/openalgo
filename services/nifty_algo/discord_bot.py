"""Dedicated Discord REST bot policy. No trading or strategy mutation imports.

HTTP interactions use Ed25519 signatures; no gateway, privileged intent, asyncio
loop or webhook-per-channel is required. Transport is called only by the
separate notification worker or explicit authenticated setup controls.
"""

import math
from datetime import UTC, datetime
from json import dumps
from re import fullmatch

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import ConfigDict, Field, field_validator, model_validator

from .models import Model

CHANNELS = (
    "critical-alerts",
    "system-warnings",
    "bot-status",
    "live-trades",
    "paper-trades",
    "shadow-trades",
    "risk-management",
    "daily-summary",
    "monthly-summary",
    "research-insights",
)
CATEGORIES = ("CRITICAL", "WARNING", "TRADE", "RISK", "STATUS", "REPORT", "RESEARCH")
COMMANDS = ("status", "position", "today", "month", "health", "report", "ack")
NO_MENTIONS = {"parse": [], "users": [], "roles": [], "replied_user": False}


def snowflake(value):
    return isinstance(value, str) and fullmatch(r"[1-9][0-9]{16,19}", value) is not None


class DiscordSettings(Model):
    model_config = ConfigDict(strict=True)
    enabled: bool = False
    application_id: str
    guild_id: str
    public_key: str
    channels: dict[str, str]
    authorized_users: list[str] = Field(default_factory=list, max_length=100)
    authorized_roles: list[str] = Field(default_factory=list, max_length=100)
    critical_role: str | None = None
    preferences: dict[str, bool] = Field(default_factory=dict)
    reminder_interval_seconds: int = Field(default=900, ge=900, le=86400)

    @field_validator("application_id", "guild_id", "critical_role")
    @classmethod
    def valid_id(cls, value):
        if value is not None and not snowflake(value):
            raise ValueError("Discord IDs must be decimal snowflakes")
        return value

    @field_validator("public_key")
    @classmethod
    def valid_public_key(cls, value):
        if fullmatch(r"[a-fA-F0-9]{64}", value) is None:
            raise ValueError("Ed25519 public key required")
        return value.lower()

    @model_validator(mode="after")
    def valid_mapping(self):
        if set(self.channels) != set(CHANNELS) or not all(
            snowflake(v) for v in self.channels.values()
        ):
            raise ValueError("All ten channel ID mappings are required")
        if any(not snowflake(v) for v in self.authorized_users + self.authorized_roles):
            raise ValueError("Invalid authorized identity")
        if not self.authorized_users and not self.authorized_roles:
            raise ValueError("At least one authorized user or role is required")
        if set(self.preferences) - set(CATEGORIES) or self.preferences.get("CRITICAL") is False:
            raise ValueError("Critical alerts cannot be disabled")
        return self


def verify_interaction(public_key, timestamp, signature, raw, now):
    """Verify exact raw bytes before parsing. Reject stale/replayed timestamps."""
    try:
        if not isinstance(timestamp, str) or not timestamp.isdecimal() or len(timestamp) > 12:
            return False
        if abs(now.timestamp() - int(timestamp)) > 300 or len(raw) > 65536:
            return False
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key)).verify(
            bytes.fromhex(signature), timestamp.encode() + raw
        )
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def event_projection(event, incident=None):
    """Small allowlisted projection; arbitrary event payloads never leave OpenAlgo."""
    kind, data = event.kind, event.payload
    if not isinstance(data, dict):
        return None
    mode, category, route = "PAPER", "STATUS", "bot-status"
    detail = {}
    if kind in ("safety_incident", "safety_acknowledged", "safety_resolved"):
        if incident is None or incident.user_id != event.user_id:
            raise ValueError("Invalid incident projection")
        mode = incident.mode
        category = "CRITICAL" if incident.severity == "CRITICAL" else "WARNING"
        route = "critical-alerts" if category == "CRITICAL" else "system-warnings"
        detail = {
            "incident_id": incident.id,
            "code": incident.code,
            "status": data.get("status", incident.status),
        }
    elif kind == "paper_fill_verified":
        category, route = "TRADE", "paper-trades"
        detail = {key: data.get(key) for key in ("order_id", "side", "quantity", "price", "fees")}
    elif kind == "shadow_activity":
        mode, category, route = "SHADOW", "TRADE", "shadow-trades"
        detail = {key: data.get(key) for key in ("shadow_id", "activity", "additive", "net")}
    elif kind == "report_generated":
        category = "REPORT"
        route = (
            "monthly-summary" if data.get("kind") in ("MONTH_END", "MILESTONE") else "daily-summary"
        )
        detail = {key: data.get(key) for key in ("report_id", "kind", "period_key")}
    elif kind in (
        "PROFIT_LOCK_ACTIVATED",
        "PROFIT_FLOOR_ACTIVATED",
        "profit_lock_activated",
        "MONTHLY_LOSS_LOCKED",
        "MONTHLY_PROFIT_LOCKED",
        "COOLDOWN_SCHEDULED",
        "trailing_stop_updated",
        "TRAILING_STOP_UPDATED",
    ):
        category, route = "RISK", "risk-management"
        detail = {key: data.get(key) for key in ("token", "stop_price", "month", "realized_net")}
    elif kind == "discord_test":
        detail = {"code": "OPERATOR_TEST"}
    else:
        return None
    occurred = (
        event.created_at.replace(tzinfo=UTC)
        if event.created_at.tzinfo is None
        else event.created_at
    )
    return route, {
        "schema_version": 1,
        "event_id": event.id,
        "kind": kind,
        "mode": mode,
        "severity": category,
        "occurred_at": occurred.isoformat(),
        **detail,
    }


def message_payload(envelope, settings, delivery_id):
    critical = envelope["severity"] == "CRITICAL"
    ping = critical and envelope.get("kind") in ("safety_incident", "incident_reminder")
    role = settings.critical_role if ping else None
    mentions = {**NO_MENTIONS, "roles": [role] if role else []}
    # Only projected scalar fields become an embed. No event data become mention syntax.
    description = "\n".join(
        f"{key}: {value}"
        for key, value in envelope.items()
        if key not in ("schema_version",) and value is not None
    )[:3500]
    return {
        "content": f"<@&{role}>" if role else "",
        "allowed_mentions": mentions,
        "nonce": str(delivery_id),
        "enforce_nonce": True,
        "embeds": [
            {
                "title": f"NIFTY {envelope['mode']} / {envelope['severity']}",
                "description": description,
                "color": 0xD32F2F if critical else 0x1565C0,
            }
        ],
    }


def command_definitions():
    definitions = [
        {
            "name": name,
            "description": f"Read NIFTY {name}",
            "type": 1,
            "default_member_permissions": "0",
            "dm_permission": False,
        }
        for name in COMMANDS
    ]
    for item in definitions:
        if item["name"] == "report":
            item["options"] = [
                {"type": 1, "name": period, "description": f"Latest {period} report"}
                for period in ("daily", "monthly")
            ]
        if item["name"] == "ack":
            item["description"] = "Acknowledge an incident; never resolves it or changes trading"
            item["options"] = [
                {
                    "type": 3,
                    "name": "incident-id",
                    "description": "Incident ID",
                    "required": True,
                    "min_length": 1,
                    "max_length": 10,
                }
            ]
    return definitions


class DiscordREST:
    """Fixed official API origin. All requests have a deadline and refuse redirects."""

    def __init__(self, token, client=None):
        if not token or len(token) > 256 or any(c.isspace() for c in token):
            raise ValueError("Discord token unavailable")
        if client is None:
            from utils.httpx_client import get_httpx_client

            client = get_httpx_client()
        self.client, self.token = client, token

    def request(self, method, path, **kwargs):
        return self.client.request(
            method,
            "https://discord.com/api/v10" + path,
            headers={
                "Authorization": "Bot " + self.token,
                "User-Agent": "OpenAlgoNiftyBot (https://github.com/Yash19815/openalgo, 1)",
            },
            timeout=5,
            follow_redirects=False,
            **kwargs,
        )

    def validate(self, settings):
        """Verify bot membership and effective permissions, including overwrites."""

        def get(path):
            response = self.request("GET", path)
            if response.status_code != 200 or len(response.content) > 1048576:
                raise ValueError("Discord configuration verification unavailable")
            return response.json()

        me = get("/users/@me")
        member = get(f"/guilds/{settings.guild_id}/members/{me['id']}")
        roles = get(f"/guilds/{settings.guild_id}/roles")
        channels = get(f"/guilds/{settings.guild_id}/channels")
        role_ids = {settings.guild_id, *member.get("roles", [])}
        base = 0
        for role in roles:
            if role["id"] in role_ids:
                base |= int(role["permissions"])
        required = (1 << 10) | (1 << 11) | (1 << 14) | (1 << 15)
        errors, critical_permissions = [], 0
        for logical, channel_id in settings.channels.items():
            channel = next((c for c in channels if c["id"] == channel_id), None)
            if channel is None or channel.get("type") not in (0, 5):
                errors.append(logical + ":INVALID_CHANNEL")
                continue
            permissions = base
            overwrites = channel.get("permission_overwrites", [])
            if not base & (1 << 3):
                everyone = next((o for o in overwrites if o["id"] == settings.guild_id), {})
                permissions = (permissions & ~int(everyone.get("deny", 0))) | int(
                    everyone.get("allow", 0)
                )
                deny, allow = 0, 0
                for overwrite in overwrites:
                    if overwrite["type"] == 0 and overwrite["id"] in role_ids - {settings.guild_id}:
                        deny |= int(overwrite["deny"])
                        allow |= int(overwrite["allow"])
                permissions = (permissions & ~deny) | allow
                specific = next(
                    (o for o in overwrites if o["type"] == 1 and o["id"] == me["id"]), {}
                )
                permissions = (permissions & ~int(specific.get("deny", 0))) | int(
                    specific.get("allow", 0)
                )
            if not base & (1 << 3) and permissions & required != required:
                errors.append(logical + ":MISSING_PERMISSIONS")
            if logical == "critical-alerts":
                critical_permissions = permissions
        if settings.critical_role:
            role = next((r for r in roles if r["id"] == settings.critical_role), None)
            if role is None or (
                not role.get("mentionable") and not critical_permissions & ((1 << 3) | (1 << 17))
            ):
                errors.append("CRITICAL_ROLE_UNMENTIONABLE")
        return {"ready": not errors, "errors": errors, "bot_id": me["id"]}

    def send(self, channel, payload, *, attachment=None):
        if not snowflake(channel):
            return {"outcome": "DEAD", "code": "INVALID_CHANNEL"}
        try:
            arguments = (
                {"json": payload}
                if attachment is None
                else {"data": {"payload_json": dumps(payload)}, "files": {"files[0]": attachment}}
            )
            response = self.request("POST", f"/channels/{channel}/messages", **arguments)
            if len(response.content) > 1048576:
                return {"outcome": "AMBIGUOUS", "code": "OVERSIZED_RESPONSE"}
            if response.status_code == 429:
                seconds = float(response.json().get("retry_after", 30))
                if not math.isfinite(seconds) or seconds <= 0:
                    seconds = 30
                return {
                    "outcome": "RETRY",
                    "code": "HTTP_429",
                    "retry_after": min(86400, max(1, math.ceil(seconds))),
                }
            if response.status_code in (200, 201):
                message_id = response.json().get("id")
                if snowflake(message_id):
                    return {
                        "outcome": "DELIVERED",
                        "code": "HTTP_ACCEPTED",
                        "message_id": message_id,
                    }
            if 400 <= response.status_code < 500:
                return {"outcome": "DEAD", "code": "HTTP_" + str(response.status_code)}
            # An HTTP 5xx or lost response may follow remote acceptance.
            return {"outcome": "AMBIGUOUS", "code": "REMOTE_OUTCOME_UNKNOWN"}
        except Exception:
            return {"outcome": "AMBIGUOUS", "code": "TRANSPORT_OUTCOME_UNKNOWN"}


def private_response(content):
    return {
        "type": 4,
        "data": {"flags": 64, "content": content[:1900], "allowed_mentions": NO_MENTIONS},
    }


def command_response(store, user_id, settings, interaction, now):
    """Signed guild interactions still require explicit server-side authorization."""
    member = interaction.get("member") or {}
    actor = (member.get("user") or {}).get("id")
    roles = member.get("roles") or []
    data = interaction.get("data") or {}
    name = data.get("name")
    if (
        interaction.get("application_id") != settings.application_id
        or interaction.get("guild_id") != settings.guild_id
        or interaction.get("channel_id") not in settings.channels.values()
        or not (actor in settings.authorized_users or set(roles) & set(settings.authorized_roles))
        or name not in COMMANDS
        or interaction.get("type") != 2
    ):
        return private_response("Not authorized or unsupported command.")
    if name == "ack":
        options = data.get("options") or []
        value = (
            options[0].get("value")
            if len(options) == 1 and options[0].get("name") == "incident-id"
            else None
        )
        if not isinstance(value, str) or fullmatch(r"[1-9][0-9]{0,9}", value) is None:
            return private_response("A valid incident ID is required.")
        return store.discord_acknowledge(
            user_id, int(value), actor, interaction["id"], now, roles=roles
        )
    if name in ("status", "health"):
        state = store.discord_status_snapshot(user_id, now)
        safety = store.safety_status(user_id)
        result = {
            "mode": "PAPER",
            "state": state["state"],
            "entry_blocked": safety["entry_blocked"],
            "runner": store.runner_status(user_id),
            "live": "LIVE_NOT_READY",
        }
        # Runner internals/configuration never leave through Discord.
        result["runner"] = (
            {k: result["runner"].get(k) for k in ("state", "updated_at")}
            if isinstance(result["runner"], dict)
            else None
        )
    elif name == "position":
        result = {
            "mode": "PAPER",
            "positions": [
                {
                    k: row.get(k)
                    for k in ("symbol", "quantity", "entry_price", "stop_price", "exit_state")
                }
                for row in store.positions(user_id)[:5]
            ],
        }
    elif name in ("today", "month"):
        from datetime import time, timedelta
        from zoneinfo import ZoneInfo

        local = now.astimezone(ZoneInfo("Asia/Kolkata"))
        day = local.date().replace(day=1) if name == "month" else local.date()
        start = datetime.combine(day, time(), tzinfo=local.tzinfo)
        snapshot = store.analytics_snapshot(
            user_id, start, max(start + timedelta(microseconds=1), now), limit=1
        )
        result = {
            "mode": "PAPER",
            "period": name,
            "metrics": {
                key: snapshot["metrics"][key]
                for key in ("total_gross", "total_net", "costs", "trades", "wins", "losses")
            },
            "risk": store.discord_status_snapshot(user_id, now)["month"],
            "unrealized": "UNAVAILABLE",
            "live": "UNAVAILABLE",
        }
    else:
        options = data.get("options") or []
        period = options[0].get("name") if len(options) == 1 else None
        if period not in ("daily", "monthly"):
            return private_response("Choose daily or monthly.")
        reports = [
            r
            for r in store.reports(user_id)
            if r["kind"] == ("MONTH_END" if period == "monthly" else "DAILY")
            and r["generation_status"] == "GENERATED"
        ]
        result = {
            "report": {k: reports[0].get(k) for k in ("id", "kind", "period_key", "sha256")}
            if reports
            else None,
            "download": "Use the authenticated OpenAlgo Reports page.",
        }
    return private_response(dumps(result, default=str, separators=(",", ":")))
