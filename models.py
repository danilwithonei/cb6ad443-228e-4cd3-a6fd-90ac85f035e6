from pydantic import BaseModel


class Payload(BaseModel):
    video_source_path: str
    img_target_path: str


class InputMessage(BaseModel):
    id: str
    payload: Payload
    created_at: str
    

class OutputMessage(BaseModel):
    id: str
    status: str
    metadata: dict | None = None
