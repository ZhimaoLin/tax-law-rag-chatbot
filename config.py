from dotenv import load_dotenv
import os


load_dotenv()


class Config:
    NEO4J_URI = os.getenv("NEO4J_URI")
    NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
    NEO4J_DATABASE = os.getenv("NEO4J_DATABASE")

    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

    VECTOR_SOURCE_PROPERTY = "text"
    VECTOR_EMBEDDING_PROPERTY = "embedding"
