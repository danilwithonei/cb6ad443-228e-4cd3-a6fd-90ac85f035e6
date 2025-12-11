from pydantic import BaseModel


class InputMessage(BaseModel):
    id: str
    image_path: str
    video_path: str


class OutputMessage(BaseModel):
    id: str
    status: str
    metadata: dict | None = None
