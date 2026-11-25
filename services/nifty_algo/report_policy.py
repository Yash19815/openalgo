"""Event kinds consumed by NIFTY reports; never a retention or deletion rule."""

REPORT_EVENT_KINDS = (
    "entry_rejected",
    "data_blocked",
    "kill-switch",
    "start",
    "pause",
    "stop",
    "MONTHLY_LOSS_LOCKED",
    "MONTHLY_PROFIT_LOCKED",
    "SESSION_LOSS_COOLDOWN",
    "COOLDOWN_SCHEDULED",
    "COOLDOWN_RECOMPUTED",
    "safety_incident",
    "safety_acknowledged",
    "safety_resolved",
    "PROFIT_LOCK_ACTIVATED",
    "PROFIT_FLOOR_UNREPRESENTABLE",
    "paper_fill_verified",
)
