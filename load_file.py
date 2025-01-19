# from pathlib import Path
# import camelot
# from pdfminer.pdfparser import PDFParser, PDFSyntaxError
# from pdfminer.pdfdocument import PDFDocument, PDFNoOutlines
import re
import pymupdf
import pymupdf4llm

# from llmsherpa.readers import LayoutPDFReader
import pathlib


PDF_PATH = "./data/instruction.pdf"
# LLMSHERPA_API_URL = "http://localhost:5010/api/parseDocument?renderFormat=all"


markdown = pymupdf4llm.to_markdown(doc=PDF_PATH, page_chunks=True)

table = 0
image = 0
graph = 0
max_level = 0

output = open("output.md", "w")

for page in markdown:
    table += len(page["tables"])
    image += len(page["images"])
    graph += len(page["graphics"])
    page_num = page["metadata"]["page"]

    text = page["text"]

    index_list = []

    toc = page["toc_items"]
    if toc:
        for header in toc:
            max_level = max(max_level, header[0])
            title = header[1]

            match = re.search(rf".*{title}.*\n", text)
            if match:
                start_idx = match.start()
                end_idx = match.end()
                index_list.append((start_idx, end_idx, title, text[start_idx : end_idx + 1]))
    else:
        match = re.search(r"[#|*]+.*\n", text)
        if match:
            start_idx = match.start()
            end_idx = match.end()
            index_list.append((start_idx, end_idx, text[start_idx : end_idx + 1], text[start_idx : end_idx + 1]))

    if index_list:
        before = text[: index_list[0][0]]
        after = text[index_list[-1][1] :]
    else:
        before = text
        after = ""
    output.write("\n===================================================\n")
    output.write(f"Page {page_num}\n")
    output.write("\n===================================================\n")

    output.write(before)
    output.write("\n===================================================\n")

    for i in range(len(index_list) - 1):
        between = text[index_list[i][1] : index_list[i + 1][0]]
        output.write("\n+++++++++++++++++++++++++++++\n")
        output.write(index_list[i][2])
        output.write(index_list[i][3])
        output.write("\n+++++++++++++++++++++++++++++\n")
        output.write(between)
        output.write("\n===================================================\n")

    if index_list:
        output.write("\n+++++++++++++++++++++++++++++\n")
        output.write(index_list[-1][2])
        output.write(index_list[-1][3])
        output.write("\n+++++++++++++++++++++++++++++\n")
    output.write(after)
    output.write("\n===================================================\n")


output.close()


# print(f"Tables: {table}")
# print(f"Images: {image}")
# print(f"Graphs: {graph}")
# print(f"Max level: {max_level}")


# pathlib.Path("output.md").write_bytes(md_text.encode())
