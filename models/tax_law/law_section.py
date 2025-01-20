from typing import Self
import uuid
from pydantic import BaseModel, Field

from models.tax_law.law_hierarchy import LawHierarchyType


class LawSection(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    hierarchy: LawHierarchyType
    title: str = ""
    text: str = ""
    page_num: int
    parent: Self = None
