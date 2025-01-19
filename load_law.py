from enum import Enum
from neo4j import Driver, GraphDatabase
from pydantic import BaseModel, Field
import pymupdf
import re
from typing import Self
import uuid

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
    section_l4 = (9, "SectionL4")
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
    elif re.match(r"\([a-z]\) [A-Z0-9]+", title):
        return LawHierarchyType.section_l1
    elif re.match(r"\(\d+\) [A-Z0-9]+", title):
        return LawHierarchyType.section_l2
    elif re.match(r"\([A-Z]\) [A-Z0-9]+", title):
        return LawHierarchyType.section_l3
    elif re.match(r"\([i|v|x]+\) ", title):
        return LawHierarchyType.section_l4
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
            MERGE (doc)-[:HAS_SECTION]->(section)
            RETURN section
        """
    elif law_section.parent and law_section.parent.hierarchy != LawHierarchyType.title:
        set_section_cypher = f"""
            MATCH (parent:{law_section.parent.hierarchy.value[1]} {{id: $parent_id}})
            MERGE (section:{law_section.hierarchy.value[1]} {{id: $id}})
            SET section.level = $level, section.hierarchy_type = $hierarchy_type, section.title = $title, section.text = $text, section.page_num = $page_num
            MERGE (parent)-[:HAS_SECTION]->(section)
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

    for hierarchy in LawHierarchyType:
        add_embedding_cypher = f"""
            MATCH (section:{hierarchy.value[1]})
            WITH section, genai.vector.encode(
                CASE
                    WHEN section.text IS NOT NULL AND section.text <> ''
                    THEN section.text
                    ELSE section.title
                END,
                'OpenAI',
                {{token: $api_key}}) AS propertyVector
            CALL db.create.setNodeVectorProperty(section, '{Config.VECTOR_EMBEDDING_PROPERTY}', propertyVector)
        """
        with kg.session(database=Config.NEO4J_DATABASE) as session:
            session.run(add_embedding_cypher, api_key=Config.OPENAI_API_KEY)

    for hierarchy in LawHierarchyType:
        create_index_cypher = f"""
            CREATE VECTOR INDEX `index_{hierarchy.value[1]}` IF NOT EXISTS
            FOR (s: {hierarchy.value[1]}) ON (s.{Config.VECTOR_EMBEDDING_PROPERTY})
        """ + """
            OPTIONS { indexConfig: {
                `vector.dimensions`: 1536,
                `vector.similarity_function`: 'cosine'
            } }
        """
        with kg.session(database=Config.NEO4J_DATABASE) as session:
            session.run(create_index_cypher)


main()
