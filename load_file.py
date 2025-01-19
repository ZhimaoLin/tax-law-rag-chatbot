import re
from typing import Self
from pydantic import BaseModel
import pymupdf4llm
from langchain_text_splitters import TokenTextSplitter


PDF_PATH = "./data/instruction.pdf"




# text_splitter = TokenTextSplitter(chunk_size=50, chunk_overlap=20)

# texts = text_splitter.split_text(state_of_the_union)
# print(texts[0])

class Header(BaseModel):
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

def connect_new_section(stack: list[Header], new_section: Header):
    if new_section.level > stack[-1].level:
        stack[-1].children.append(new_section)
        new_section.parent = stack[-1]
    else:
        while new_section.level <= stack[-1].level:
            stack.pop()
        stack[-1].children.append(new_section)
        new_section.parent = stack[-1]
    stack.append(new_section)


def main():
    markdown = pymupdf4llm.to_markdown(doc=PDF_PATH, page_chunks=True)

    head = Header(level=0, page_num=0)
    stack = [head]

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

        # Some content is not in order when parsing the PDF
        content_list.sort()

        if content_list:
            before = text[: content_list[0][0]]
            after = text[content_list[-1][1] :]

            for i in range(len(content_list) - 1):
                between = text[content_list[i][1] : content_list[i + 1][0]]
                new_section = Header(level=content_list[i][2], title=content_list[i][3], text=between, page_num=page_num)
                connect_new_section(stack, new_section)
            
            new_section2 = Header(level=content_list[-1][2], title=content_list[-1][3], text=after, page_num=page_num)
            connect_new_section(stack, new_section2)
        else:
            before = text

        stack[-1].text += before


    print(head)

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
