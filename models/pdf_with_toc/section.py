from typing import Self
import uuid

from pydantic import BaseModel, Field


class Section(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    level: int
    title: str = ""
    text: str = ""
    page_num: int
    parent: Self = None
    children: list[Self] = []

    def __str__(self) -> str:
        return "\n".join(self.text)
