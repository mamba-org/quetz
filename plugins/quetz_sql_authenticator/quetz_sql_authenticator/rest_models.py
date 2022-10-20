from pydantic import BaseModel


class Credential(BaseModel):
    username: str
