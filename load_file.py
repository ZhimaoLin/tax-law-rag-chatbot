import re
from typing import Self
import uuid
from pydantic import BaseModel, Field
import pymupdf4llm
from langchain_text_splitters import TokenTextSplitter

from neo4j import Driver, GraphDatabase

from config import Config


PDF_PATH = "./data/instruction.pdf"


# text_splitter = TokenTextSplitter(chunk_size=50, chunk_overlap=20)

# texts = text_splitter.split_text(state_of_the_union)
# print(texts[0])


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


def find_markdown_header(regex: str, text: str) -> tuple[int, int] | None:
    match = re.search(regex, text)
    if match:
        start_idx = match.start()
        end_idx = match.end()
        return (start_idx, end_idx)
    return None


def connect_new_section(stack: list[Section], new_section: Section, kg: Driver) -> None:
    if new_section.level > stack[-1].level:
        new_section.parent = stack[-1]
    else:
        while new_section.level <= stack[-1].level:
            node = stack.pop()
            set_section_node(kg, node)
        new_section.parent = stack[-1]
    stack.append(new_section)
    set_section_node(kg, new_section)


def connect_neo4j_db() -> None:
    kg = GraphDatabase.driver(Config.NEO4J_URI, auth=(Config.NEO4J_USERNAME, Config.NEO4J_PASSWORD))
    kg.verify_connectivity()
    return kg


def set_document_node(kg: Driver, section: Section) -> None:
    set_document_cypher = """
        MERGE (doc:Document {id: $id})
        SET doc.level = $level, doc.title = $title, doc.text = $text, doc.page_num = $page_num
        RETURN doc
    """
    with kg.session(database=Config.NEO4J_DATABASE) as session:
        session.run(
            set_document_cypher, id=str(section.id), level=0, title=section.title, text=section.text, page_num=section.page_num
        )


def set_section_node(kg: Driver, section: Section) -> None:
    if section.parent and section.parent.level == 0:
        set_section_cypher = """
            MATCH (doc:Document {id: $parent_id})
            MERGE (section:Section {id: $id})
            SET section.level = $level, section.title = $title, section.text = $text, section.page_num = $page_num
            MERGE (doc)-[:HAS_SECTION]->(section)
            RETURN section
        """
    elif section.parent and section.parent.level > 0:
        set_section_cypher = """
            MATCH (parent:Section {id: $parent_id})
            MERGE (section:Section {id: $id})
            SET section.level = $level, section.title = $title, section.text = $text, section.page_num = $page_num
            MERGE (parent)-[:HAS_SECTION]->(section)
            RETURN section
        """
    else:
        raise ValueError("Section must have a parent")

    with kg.session(database=Config.NEO4J_DATABASE) as session:
        session.run(
            set_section_cypher,
            parent_id=str(section.parent.id),
            id=str(section.id),
            level=section.level,
            title=section.title,
            text=section.text,
            page_num=section.page_num,
        )


def main():
    kg = connect_neo4j_db()

    markdown = pymupdf4llm.to_markdown(doc=PDF_PATH, page_chunks=True)

    head = Section(level=0, page_num=0)
    stack = [head]
    set_document_node(kg, head)

    for page in markdown:
        page_num = page["metadata"]["page"]
        text = page["text"]
        toc = page["toc_items"]

        content_list = []
        for header in toc:
            level = header[0]
            title = header[1]

            result = find_markdown_header(rf"[#|*| ]*{title}.*\n", text)
            if result:
                start_idx, end_idx = result
                content_list.append((start_idx, end_idx, level, title))

        # Some content is not in order when parsing the multi-column PDFs
        content_list.sort()

        if content_list:
            before = text[: content_list[0][0]]
            after = text[content_list[-1][1] :]
            stack[-1].text += before

            for i in range(len(content_list) - 1):
                between = text[content_list[i][1] : content_list[i + 1][0]]
                new_section = Section(level=content_list[i][2], title=content_list[i][3], text=between, page_num=page_num)
                connect_new_section(stack, new_section, kg)

            new_section2 = Section(level=content_list[-1][2], title=content_list[-1][3], text=after, page_num=page_num)
            connect_new_section(stack, new_section2, kg)
        else:
            before = text
            stack[-1].text += before

    while stack:
        node = stack.pop()
        if node.level > 0:
            set_section_node(kg, node)
        else:
            set_document_node(kg, node)


main()


# else:
#     match = re.search(r"[#|*]+.*\n", text)
#     if match:
#         start_idx = match.start()
#         end_idx = match.end()
#         index_list.append((start_idx, end_idx, text[start_idx : end_idx + 1], text[start_idx : end_idx + 1]))

# index_list.sort()

# if index_list:
#     before = text[: index_list[0][0]]
#     after = text[index_list[-1][1] :]
# else:
#     before = text
#     after = ""
# output.write("\n===================================================\n")
# output.write(f"Page {page_num}\n")
# output.write("\n===================================================\n")

# output.write(before)
# output.write("\n===================================================\n")

# for i in range(len(index_list) - 1):
#     between = text[index_list[i][1] : index_list[i + 1][0]]
#     output.write("\n+++++++++++++++++++++++++++++\n")
#     output.write(index_list[i][2])
#     print("\n")
#     output.write(index_list[i][3])
#     output.write("\n+++++++++++++++++++++++++++++\n")
#     output.write(between)
#     output.write("\n===================================================\n")

# if index_list:
#     output.write("\n+++++++++++++++++++++++++++++\n")
#     output.write(index_list[-1][2])
#     print("\n")
#     output.write(index_list[-1][3])
#     output.write("\n+++++++++++++++++++++++++++++\n")
# output.write(after)
# output.write("\n===================================================\n")


# output.close()


# print(f"Tables: {table}")
# print(f"Images: {image}")
# print(f"Graphs: {graph}")
# print(f"Max level: {max_level}")


# pathlib.Path("output.md").write_bytes(md_text.encode())
