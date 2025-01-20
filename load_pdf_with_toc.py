import pymupdf4llm
import re

from models.neo4j_db import Neo4jDB
from models.section import Section
from models.hierarchy_type import HierarchyType


PDF_PATH = "./data/test.pdf"


def find_markdown_header(regex: str, text: str) -> tuple[int, int] | None:
    match = re.search(regex, text)
    if match:
        start_idx = match.start()
        end_idx = match.end()
        return (start_idx, end_idx)
    return None


def connect_new_section(stack: list[Section], new_section: Section, neo4j_db: Neo4jDB) -> None:
    if new_section.level > stack[-1].level:
        new_section.parent = stack[-1]
    else:
        while new_section.level <= stack[-1].level:
            node = stack.pop()
            neo4j_db.set_section_node(node)
        new_section.parent = stack[-1]
    stack.append(new_section)
    neo4j_db.set_section_node(new_section)


def main():
    neo4j_db = Neo4jDB()

    markdown = pymupdf4llm.to_markdown(doc=PDF_PATH, page_chunks=True)

    print(f"Starting to load {len(markdown)} pages to Neo4j")

    head = Section(
        level=HierarchyType.document.value[0], hierarchy=HierarchyType.document, page_num=1, title="1040 Instructions"
    )
    stack = [head]
    neo4j_db.set_document_node(head)

    for page in markdown:
        page_num = page["metadata"]["page"]
        print(f"Processing page {page_num} of {len(markdown)}")

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
                connect_new_section(stack, new_section, neo4j_db)

            new_section2 = Section(level=content_list[-1][2], title=content_list[-1][3], text=after, page_num=page_num)
            connect_new_section(stack, new_section2, neo4j_db)
        else:
            before = text
            stack[-1].text += before

    while stack:
        node = stack.pop()
        if node.level > 0:
            neo4j_db.set_section_node(node)
        else:
            neo4j_db.set_document_node(node)

    # splitting chunks
    neo4j_db.create_chunk_node()

    neo4j_db.add_embedding(label="Document")
    neo4j_db.add_embedding(label="Section")
    neo4j_db.create_vector_index(label="Document")
    neo4j_db.create_vector_index(label="Section")

    print(f"Finished loading {len(markdown)} pages to Neo4j")


if __name__ == "__main__":
    main()
