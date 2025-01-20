from enum import Enum
import re
from typing import Self


class HierarchyType(Enum):
    document = (0, "Document")
    subtitle = (1, "Subtitle")
    chapter = (2, "Chapter")
    subchapter = (3, "Subchapter")
    part = (4, "Part")
    section = (5, "Section")
    section_l1 = (6, "SectionL1")
    section_l2 = (7, "SectionL2")
    section_l3 = (8, "SectionL3")
    section_l4 = (9, "SectionL4")
    table_of_contents = (5, "TableOfContents")
    editorial_notes = (5, "EditorialNotes")
    amendments = (6, "Amendments")
    chunk = (10, "Chunk")

    @classmethod
    def check_hierarchy_type(self, title: str) -> Self:
        if "subtitle" in title.lower():
            return self.subtitle
        elif "chapter" in title.lower():
            return self.chapter
        elif "subchapter" in title.lower():
            return self.subchapter
        elif "part" in title.lower():
            return self.part
        elif "§" in title:
            return self.section
        elif "table of contents" in title.lower():
            return self.table_of_contents
        elif "editorial notes" in title.lower():
            return self.editorial_notes
        elif "amendments" in title.lower():
            return self.amendments
        elif re.match(r"\([a-z]\) [A-Z0-9]+", title):
            return self.section_l1
        elif re.match(r"\(\d+\) [A-Z0-9]+", title):
            return self.section_l2
        elif re.match(r"\([A-Z]\) [A-Z0-9]+", title):
            return self.section_l3
        elif re.match(r"\([i|v|x]+\) ", title):
            return self.section_l4
        elif "chunk" in title.lower():
            return self.chunk
        else:
            return self.document
