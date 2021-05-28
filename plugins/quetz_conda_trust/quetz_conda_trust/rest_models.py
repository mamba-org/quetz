from pydantic import BaseModel


class SigningKey(BaseModel):
    channel: str
    private_key: str
