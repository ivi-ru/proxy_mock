from datetime import datetime
from zoneinfo import ZoneInfo


def now_msk_iso() -> str:
    return datetime.now(ZoneInfo("Europe/Moscow")).isoformat()
