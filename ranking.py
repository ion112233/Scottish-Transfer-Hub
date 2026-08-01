"""
Scores a transfer for "how interesting is this" as a blend of the fee, the
player's market value (a proxy for how notable they are), and how prominent
the clubs involved are.
"""
import math

import config

_FEE_BASELINE = {
    "fee": None,       # computed from fee_eur
    "free": 0.15,       # still could be a notable free-agent departure
    "loan_fee": None,   # computed from fee_eur
    "loan": 0.10,
    "unknown": 0.05,
}


def _log_scale(amount: int, cap: int) -> float:
    return min(1.0, math.log1p(amount) / math.log1p(cap))


def _fee_score(transfer: dict) -> float:
    fee_eur = transfer.get("fee_eur")
    if transfer["fee_type"] in ("fee", "loan_fee") and fee_eur is not None:
        return _log_scale(fee_eur, config.FEE_CAP_EUR)
    return _FEE_BASELINE.get(transfer["fee_type"], 0.05)


def _market_value_score(transfer: dict) -> float:
    mv = transfer.get("market_value_eur")
    if not mv:
        return 0.0
    return _log_scale(mv, config.MARKET_VALUE_CAP_EUR)


def _club_score(transfer: dict) -> float:
    from_weight = config.CLUB_WEIGHTS.get(transfer.get("from_club_id"), config.OTHER_CLUB_WEIGHT)
    to_weight = config.CLUB_WEIGHTS.get(transfer.get("to_club_id"), config.OTHER_CLUB_WEIGHT)
    return max(from_weight, to_weight) / 10.0


def score(transfer: dict) -> float:
    return (
        config.FEE_WEIGHT * _fee_score(transfer)
        + config.MARKET_VALUE_WEIGHT * _market_value_score(transfer)
        + config.CLUB_WEIGHT * _club_score(transfer)
    )


def rank(transfers: list[dict]) -> list[dict]:
    """Returns transfers sorted most-interesting first, each tagged with 'score'."""
    for t in transfers:
        t["score"] = score(t)
    return sorted(transfers, key=lambda t: t["score"], reverse=True)
