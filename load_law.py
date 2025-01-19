from enum import Enum
import re
from typing import Self
import uuid
from llmsherpa.readers import LayoutPDFReader
import json
from pathlib import Path
from neo4j import Driver, GraphDatabase
from pydantic import BaseModel, Field
import pymupdf
import pymupdf4llm

from config import Config


PDF_PATH = "./data/code.pdf"
LLMSHERPA_API_URL = "http://localhost:5010/api/parseDocument?renderFormat=all"


class LawHierarchyType(Enum):
    title = (0, "Title")
    subtitle = (1, "Subtitle")
    chapter = (2, "Chapter")
    subchapter = (3, "Subchapter")
    part = (4, "Part")
    section = (5, "Section")
    section_l1 = (6, "SectionL1")
    section_l2 = (7, "SectionL2")
    section_l3 = (8, "SectionL3")
    table_of_contents = (5, "TableOfContents")
    editorial_notes = (5, "EditorialNotes")
    amendments = (6, "Amendments")


class LawSection(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    hierarchy: LawHierarchyType
    title: str = ""
    text: str = ""
    page_num: int
    parent: Self = None


def check_hierarchy_type(title: str) -> LawHierarchyType:
    if "subtitle" in title.lower():
        return LawHierarchyType.subtitle
    elif "chapter" in title.lower():
        return LawHierarchyType.chapter
    elif "subchapter" in title.lower():
        return LawHierarchyType.subchapter
    elif "part" in title.lower():
        return LawHierarchyType.part
    elif "§" in title:
        return LawHierarchyType.section
    elif "table of contents" in title.lower():
        return LawHierarchyType.table_of_contents
    elif "editorial notes" in title.lower():
        return LawHierarchyType.editorial_notes
    elif "amendments" in title.lower():
        return LawHierarchyType.amendments
    elif re.match(r"\([a-z]\)", title):
        return LawHierarchyType.section_l1
    elif re.match(r"\(\d+\)", title):
        return LawHierarchyType.section_l2
    elif re.match(r"\([A-Z]\)", title):
        return LawHierarchyType.section_l3
    else:
        raise ValueError("Unknown Hierarchy Type")


def split_by_header(regex: str, text: str, page_num: int) -> tuple[str, list[LawSection]]:
    match = re.split(regex, text)
    before = ""
    between = []
    if match:
        before = match[0]
        for i in range(1, len(match) - 1, 2):
            title = match[i]
            content = match[i + 1]
            hierarchy_type = check_hierarchy_type(title)
            # if hierarchy_type == LawHierarchyType.section:
            #     print(f"Found Section: {title}")
            new_section = LawSection(hierarchy=hierarchy_type, title=title, text=content, page_num=page_num)
            between.append(new_section)
    else:
        before = text
    return before, between


def connect_new_section(stack: list[LawSection], new_section: LawSection, kg: Driver) -> None:
    if new_section.hierarchy > stack[-1].hierarchy:
        new_section.parent = stack[-1]
    else:
        while new_section.hierarchy <= stack[-1].hierarchy:
            node = stack.pop()
            set_section_node(kg, node)
        new_section.parent = stack[-1]
    stack.append(new_section)
    set_section_node(kg, new_section)


def connect_neo4j_db() -> None:
    kg = GraphDatabase.driver(Config.NEO4J_URI, auth=(Config.NEO4J_USERNAME, Config.NEO4J_PASSWORD))
    kg.verify_connectivity()
    return kg


def set_document_node(kg: Driver, law_section: LawSection) -> None:
    set_document_cypher = """
        MERGE (doc:Document {id: $id})
        SET doc.level = $level, doc.hierarchy_type = $hierarchy_type, doc.title = $title, doc.text = $text, doc.page_num = $page_num
        RETURN doc
    """
    with kg.session(database=Config.NEO4J_DATABASE) as session:
        session.run(
            set_document_cypher,
            id=str(law_section.id),
            level=LawHierarchyType.title.value[0],
            hierarchy_type=LawHierarchyType.title.value[1],
            title=law_section.title,
            text=law_section.text,
            page_num=law_section.page_num,
        )


def set_section_node(kg: Driver, law_section: LawSection) -> None:
    if law_section.parent and law_section.parent.hierarchy == LawHierarchyType.title:
        set_section_cypher = f"""
            MATCH (doc:Document {{id: $parent_id}})
            MERGE (section:{law_section.hierarchy.value[1]} {{id: $id}})
            SET section.level = $level, section.hierarchy_type = $hierarchy_type, section.title = $title, section.text = $text, section.page_num = $page_num
            MERGE (section)-[:BELONGS_TO]->(doc)
            RETURN section
        """
    elif law_section.parent and law_section.parent.hierarchy != LawHierarchyType.title:
        set_section_cypher = f"""
            MATCH (parent:{law_section.parent.hierarchy.value[1]} {{id: $parent_id}})
            MERGE (section:{law_section.hierarchy.value[1]} {{id: $id}})
            SET section.level = $level, section.hierarchy_type = $hierarchy_type, section.title = $title, section.text = $text, section.page_num = $page_num
            MERGE (section)-[:BELONGS_TO]->(parent)
            RETURN section
        """
    else:
        raise ValueError("Section must have a parent")

    print(f"Writing Section: ID: {law_section.id}, Title: {law_section.title}, Page: {law_section.page_num}")

    with kg.session(database=Config.NEO4J_DATABASE) as session:
        session.run(
            set_section_cypher,
            parent_id=str(law_section.parent.id),
            id=str(law_section.id),
            level=law_section.hierarchy.value[0],
            hierarchy_type=law_section.hierarchy.value[1],
            title=law_section.title,
            text=law_section.text,
            page_num=law_section.page_num,
        )


def main():
    kg = connect_neo4j_db()
    pdf = pymupdf.open(PDF_PATH)

    head = LawSection(hierarchy=LawHierarchyType.title, title="INTERNAL REVENUE TITLE", page_num=0)
    stack = [head]
    set_document_node(kg, head)

    for i, page in enumerate(pdf[86:95]):
        page_num = i + 1

        text = page.get_text()

        regex = r"((?:Subtitle [A-Z]|CHAPTER \d+|Subchapter [A-Z]|PART [I|V|X|L|C|D|M]+|§\d+\.|TABLE OF CONTENTS|EDITORIAL NOTES|AMENDMENTS|\([a-z]\) |\(\d+\) |\([A-Z]\) ).*)\n"

        before, between = split_by_header(regex=regex, text=text, page_num=page_num)
        stack[-1].text += before

        for section in between:
            if section.hierarchy.value[0] > stack[-1].hierarchy.value[0]:
                section.parent = stack[-1]
            else:
                while section.hierarchy.value[0] <= stack[-1].hierarchy.value[0]:
                    node = stack.pop()
                    set_section_node(kg, node)
                section.parent = stack[-1]
            stack.append(section)
            set_section_node(kg, section)

    while stack:
        node = stack.pop()
        if node.hierarchy == LawHierarchyType.title:
            set_document_node(kg, node)
        else:
            set_section_node(kg, node)


main()


# pdf_reader = LayoutPDFReader(LLMSHERPA_API_URL)
# doc = pdf_reader.read_pdf(PDF_PATH)

# with open("output.json", "w") as file:
#     json.dump(doc.json, file)


# markdown = pymupdf4llm.to_markdown(doc=PDF_PATH, page_chunks=True, pages=[86, 87, 88, 89, 90, 91, 92])

# for page in markdown:
#     with open(f"./test/markdown/{page['metadata']['page']}.md", "w") as file:
#         file.write(page["text"])

# doc = pymupdf.open(PDF_PATH) # open a document

# for page in doc[86:92]:
#     text = page.get_text() # extract text from the page
#     print(text) # print

# raise Exception("Stop here")

# total_pages = len(doc) # get the total number of pages in the document
# chunk_size = 10 # set the chunk size

# for i in range(0, total_pages, chunk_size):
#     # Create a new PDF document for the chunk
#     end_page = min(i + chunk_size - 1, total_pages - 1)

#     new_pdf = pymupdf.open()
#     new_pdf.insert_pdf(doc, from_page=i, to_page=end_page)

#     chunk_number = (i // chunk_size) + 1
#     pdf_chunk_name = f"chunk_{chunk_number}_{i+1}_{end_page+1}.pdf"
#     output_pdf = f"./test/{pdf_chunk_name}.pdf"
#     new_pdf.save(output_pdf)
#     new_pdf.close()


#     pdf_chunk = pdf_reader.read_pdf(output_pdf)
#     with open(f"./test/json/{pdf_chunk_name}.json", "w") as file:
#         try:
#             json_object = json.dump(pdf_chunk.json, indent=4)
#             file.write(json_object)
#             if not json_object:
#                 print(f"Error in {pdf_chunk_name}: It is empty")
#         except:
#             print(f"Error in {pdf_chunk_name}")


# for page_num in range(len(doc)):
#     page = doc[page_num] # get a page
#     text = page.get_text("text") # extract text from the page
#     print(text) # print the text
