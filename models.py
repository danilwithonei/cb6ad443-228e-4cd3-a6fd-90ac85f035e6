from pydantic import BaseModel
from enum import Enum


class MessageType(str, Enum):
    in_process = "in_process"
    done = "done"
    no_target_face = "no_target_face"


class ProcessingMetadata(BaseModel):
    total_frames: int
    current_frame: int


class DoneMetadata(BaseModel):
    result_path: str


class Payload(BaseModel):
    video_source_path: str
    img_target_path: str


class InputMessage(BaseModel):
    id: str
    client_id: str
    payload: Payload
    created_at: str


class OutputMessage(BaseModel):
    id: str
    client_id: str
    message_type: MessageType
    metadata: ProcessingMetadata | DoneMetadata
