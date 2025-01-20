from pinecone.grpc import PineconeGRPC as Pinecone

from config import Config


class PineconeDB:
    def __init__(self):
        self.pc = Pinecone(api_key=Config.PINECONE_API_KEY)
        self.index = self.pc.Index(Config.PINECONE_INDEX_NAME)

    def upsert(self, records: list[dict]) -> None:
        self.index.upsert(vectors=records)

    def query(self, query_embedding: list[float], top_k: int = 1) -> list[dict]:
        results = self.index.query(vector=query_embedding, top_k=top_k, include_metadata=True)
        return results
