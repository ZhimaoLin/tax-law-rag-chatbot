import pymupdf
import re

from models.neo4j_db import Neo4jDB
from models.section import Section
from models.hierarchy_type import HierarchyType


PDF_PATH = "./data/test.pdf"


def split_by_header(regex: str, text: str, page_num: int) -> tuple[str, list[Section]]:
    match = re.split(regex, text)
    before = ""
    between = []
    if match:
        before = match[0]
        for i in range(1, len(match) - 1, 2):
            title = match[i]
            content = match[i + 1]
            hierarchy = HierarchyType.check_hierarchy_type(title)
            level = hierarchy.value[0]
            new_section = Section(level=level, hierarchy=hierarchy, title=title, text=content, page_num=page_num)
            between.append(new_section)
    else:
        before = text
    return before, between


def main():
    neo4j_db = Neo4jDB()
    pdf = pymupdf.open(PDF_PATH)

    print(f"Starting to load {len(pdf)} pages to Neo4j")

    head = Section(
        level=HierarchyType.document.value[0], hierarchy=HierarchyType.document, title="INTERNAL REVENUE TITLE", page_num=1
    )
    stack = [head]
    neo4j_db.set_document_node(head)

    for i, page in enumerate(pdf):
        page_num = i + 1
        print(f"Processing page {page_num} of {len(pdf)}")

        text = page.get_text()

        regex = r"((?:Subtitle [A-Z]|CHAPTER \d+|Subchapter [A-Z]|PART [I|V|X|L|C|D|M]+|§\d+\.|TABLE OF CONTENTS|EDITORIAL NOTES|AMENDMENTS|\([a-z]\) [A-Z0-9]+|\(\d+\) [A-Z0-9]+|\([A-Z]\) [A-Z0-9]+|\([i|v|x]+\) ).*)\n"

        before, between = split_by_header(regex=regex, text=text, page_num=page_num)
        stack[-1].text += before

        for section in between:
            if section.hierarchy.value[0] > stack[-1].hierarchy.value[0]:
                section.parent = stack[-1]
            else:
                while section.hierarchy.value[0] <= stack[-1].hierarchy.value[0]:
                    node = stack.pop()
                    neo4j_db.set_section_node(node)
                section.parent = stack[-1]
            stack.append(section)
            neo4j_db.set_section_node(section)

    while stack:
        node = stack.pop()
        if node.hierarchy == HierarchyType.document:
            neo4j_db.set_document_node(node)
        else:
            neo4j_db.set_section_node(node)

    # Split into chunks
    neo4j_db.create_chunk_node()

    for hierarchy in HierarchyType:
        label = hierarchy.value[1]
        neo4j_db.add_embedding(label)
        neo4j_db.create_vector_index(label)

    print(f"Finished loading {len(pdf)} pages to Neo4j")


if __name__ == "__main__":
    main()
