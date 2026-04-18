from pydantic import BaseModel


class ActionRequest(BaseModel):
    game_id: str
    player_id: str
    action: str


class ActionResponse(BaseModel):
    accepted: bool
    message: str
