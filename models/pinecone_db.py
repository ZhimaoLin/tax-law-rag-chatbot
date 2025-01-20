from langchain_text_splitters import CharacterTextSplitter
from pinecone.grpc import PineconeGRPC as Pinecone

from config import Config


class PineconeDB:
    def __init__(self):
        self.pc = Pinecone(api_key=Config.PINECONE_API_KEY)
        self.index = self.pc.Index(Config.PINECONE_INDEX_NAME)

    def upsert(self, records: list[dict]) -> None:
        self.index.upsert(vectors=records)
