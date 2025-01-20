import uuid
from langchain_text_splitters import CharacterTextSplitter
from openai import OpenAI
import pymupdf

from config import Config
from models.pinecone_db import PineconeDB


PDF_PATH = "./data/test.pdf"


def main():
    pc = PineconeDB()
    text_splitter = CharacterTextSplitter.from_tiktoken_encoder(
        encoding_name=Config.TOKEN_ENCODING, chunk_size=Config.CHUNK_SIZE, chunk_overlap=Config.OVERLAP_SIZE
    )
    client = OpenAI()

    pdf = pymupdf.open(PDF_PATH)
    print(f"Starting to load {len(pdf)} pages to Pinecone")

    for i, page in enumerate(pdf):
        page_num = i + 1
        print(f"Processing page {page_num} of {len(pdf)}")

        text = page.get_text()

        chunk_list = text_splitter.split_text(text)

        to_upsert_queue = []
        for chunk in chunk_list:

            response = client.embeddings.create(input=chunk, model="text-embedding-3-large")
            embedding = response.data[0].embedding

            data = {
                "id": str(uuid.uuid4()),
                "values": embedding,
                "metadata": {
                    "text": chunk,
                    "page_num": page_num,
                },
            }
            to_upsert_queue.append(data)

        pc.upsert(to_upsert_queue)

    print(f"Finished loading {len(pdf)} pages to Pinecone")


if __name__ == "__main__":
    main()
