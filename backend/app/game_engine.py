from collections.abc import Iterable


VALID_ACTIONS = {
    "roll_dice",
    "buy_property",
    "skip_buy",
    "bank_deposit",
    "bank_withdraw",
    "propose_alliance",
    "accept_alliance",
    "reject_alliance",
    "pass",
}


def validate_action(action: str, allowed_actions: Iterable[str]) -> bool:
    if action not in VALID_ACTIONS:
        return False
    return action in set(allowed_actions)
