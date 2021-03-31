from typing import List

from pydantic import BaseModel


class SolveTask(BaseModel):
    channels: List[str]
    subdir: str
    spec: List[str]
