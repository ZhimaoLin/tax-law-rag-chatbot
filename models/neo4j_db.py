from neo4j import GraphDatabase

from config import Config


def connect_neo4j_db() -> None:
    kg = GraphDatabase.driver(Config.NEO4J_URI, auth=(Config.NEO4J_USERNAME, Config.NEO4J_PASSWORD))
    kg.verify_connectivity()
    return kg
