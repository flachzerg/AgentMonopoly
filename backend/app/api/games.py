from fastapi import APIRouter

from app.agent_runtime import decide_fallback
from app.game_engine import validate_action
from app.schemas import ActionRequest, ActionResponse

router = APIRouter(prefix="/games", tags=["games"])


@router.post("/action", response_model=ActionResponse)
def submit_action(payload: ActionRequest) -> ActionResponse:
    allowed_actions = ["roll_dice", "buy_property", "skip_buy", "pass"]
    if validate_action(payload.action, allowed_actions):
        return ActionResponse(accepted=True, message="action accepted")
    return ActionResponse(accepted=False, message="invalid action")


@router.get("/{game_id}/agent/{player_id}")
def agent_act(game_id: str, player_id: str) -> dict:
    allowed_actions = ["roll_dice", "pass"]
    decision = decide_fallback(allowed_actions)
    return {
        "game_id": game_id,
        "player_id": player_id,
        "decision": decision.model_dump(),
    }
