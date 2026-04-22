from pydantic import BaseModel


class GenerateContractBody(BaseModel):
    request_id: str
    result_id: str


class ReviseBody(BaseModel):
    revision_note: str
