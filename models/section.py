from pydantic import BaseModel, Field
from typing import Self
import uuid

from models.hierarchy_type import HierarchyType


class Section(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    level: int
    hierarchy: HierarchyType = HierarchyType.section
    title: str = ""
    text: str = ""
    page_num: int
    parent: Self = None

    def __str__(self) -> str:
        return "\n".join(self.text)
