from pydantic import BaseModel


class AgentDecision(BaseModel):
    action: str
    reason: str


def decide_fallback(allowed_actions: list[str]) -> AgentDecision:
    action = "pass"
    if "roll_dice" in allowed_actions:
        action = "roll_dice"
    elif allowed_actions:
        action = allowed_actions[0]
    return AgentDecision(action=action, reason="fallback strategy for MVP")
