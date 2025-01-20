from neo4j import GraphDatabase

from config import Config
from models.pdf_with_toc.section import Section


# def connect_neo4j_db() -> None:
#     kg = GraphDatabase.driver(Config.NEO4J_URI, auth=(Config.NEO4J_USERNAME, Config.NEO4J_PASSWORD))
#     kg.verify_connectivity()
#     return kg


class Neo4jDB:
    def __init__(self):
        kg = GraphDatabase.driver(Config.NEO4J_URI, auth=(Config.NEO4J_USERNAME, Config.NEO4J_PASSWORD))
        kg.verify_connectivity()
        self.kg = kg

    # region Embedding
    def add_embedding(self, label: str):
        add_embedding_cypher = f"""
            MATCH (section:{label})
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
        with self.kg.session(database=Config.NEO4J_DATABASE) as session:
            session.run(add_embedding_cypher, api_key=Config.OPENAI_API_KEY)

    def create_vector_index(self, label: str):
        create_index_cypher = (
            f"""
            CREATE VECTOR INDEX `index_{label}` IF NOT EXISTS
            FOR (s: {label}) ON (s.{Config.VECTOR_EMBEDDING_PROPERTY})
        """
            + """
            OPTIONS { indexConfig: {
                `vector.dimensions`: 1536,
                `vector.similarity_function`: 'cosine'
            } }
        """
        )
        with self.kg.session(database=Config.NEO4J_DATABASE) as session:
            session.run(create_index_cypher)

    # endregion

    # region Tax Law
    # endregion

    # region PDF with TOC
    def set_document_node_for_section(self, section: Section) -> None:
        set_document_cypher = """
            MERGE (doc:Document {id: $id})
            SET doc.level = $level, doc.title = $title, doc.text = $text, doc.page_num = $page_num
            RETURN doc
        """
        with self.kg.session(database=Config.NEO4J_DATABASE) as session:
            session.run(
                set_document_cypher,
                id=str(section.id),
                level=0,
                title=section.title,
                text=section.text,
                page_num=section.page_num,
            )

    def set_section_node(self, section: Section) -> None:
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

        with self.kg.session(database=Config.NEO4J_DATABASE) as session:
            session.run(
                set_section_cypher,
                parent_id=str(section.parent.id),
                id=str(section.id),
                level=section.level,
                title=section.title,
                text=section.text,
                page_num=section.page_num,
            )

    # endregion
