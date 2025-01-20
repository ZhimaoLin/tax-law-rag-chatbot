import pymupdf
import re

from models.neo4j_db import Neo4jDB
from models.tax_law.law_hierarchy import LawHierarchyType
from models.tax_law.law_section import LawSection


PDF_PATH = "./data/code.pdf"


def split_by_header(regex: str, text: str, page_num: int) -> tuple[str, list[LawSection]]:
    match = re.split(regex, text)
    before = ""
    between = []
    if match:
        before = match[0]
        for i in range(1, len(match) - 1, 2):
            title = match[i]
            content = match[i + 1]
            hierarchy_type = LawHierarchyType.check_hierarchy_type(title)
            new_section = LawSection(hierarchy=hierarchy_type, title=title, text=content, page_num=page_num)
            between.append(new_section)
    else:
        before = text
    return before, between


def main():
    neo4j_db = Neo4jDB()
    pdf = pymupdf.open(PDF_PATH)

    head = LawSection(hierarchy=LawHierarchyType.document, title="INTERNAL REVENUE TITLE", page_num=0)
    stack = [head]
    neo4j_db.set_document_node_for_law_section(head)

    for i, page in enumerate(pdf[86:102]):
        page_num = i + 1

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
        if node.hierarchy == LawHierarchyType.document:
            neo4j_db.set_document_node_for_law_section(node)
        else:
            neo4j_db.set_section_node(node)

    for hierarchy in LawHierarchyType:
        label = hierarchy.value[1]
        neo4j_db.add_embedding(label)
        neo4j_db.create_vector_index(label)


if __name__ == "__main__":
    main()
