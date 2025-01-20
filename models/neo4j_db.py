from langchain_text_splitters import CharacterTextSplitter
from neo4j import GraphDatabase
import uuid

from config import Config
from models.pdf_with_toc.section import Section
from models.tax_law.law_hierarchy import LawHierarchyType
from models.tax_law.law_section import LawSection


class Neo4jDB:
    def __init__(self):
        kg = GraphDatabase.driver(Config.NEO4J_URI, auth=(Config.NEO4J_USERNAME, Config.NEO4J_PASSWORD))
        kg.verify_connectivity()
        self.kg = kg

    def create_chunk_node_for_section(self) -> None:
        query_all_sections = """
            MATCH (section:Section)
            RETURN section
        """
        with self.kg.session(database=Config.NEO4J_DATABASE) as session:
            all_sections = session.run(query_all_sections)

            for record in all_sections:
                parent = record["section"]
                parent_id = parent["id"]
                level = parent["level"]
                title = parent["title"]
                text = parent["text"]
                page_num = parent["page_num"]

                if len(text) > 15000:
                    text_splitter = CharacterTextSplitter.from_tiktoken_encoder(
                        encoding_name="cl100k_base", chunk_size=1000, chunk_overlap=100
                    )
                    chunk_list = text_splitter.split_text(text)
                    for chunk in chunk_list:
                        create_chunk_cypher = """
                            MERGE (chunk:Chunk {id: $id})
                            ON CREATE SET chunk.level = $level, chunk.title = $title, chunk.text = $text, chunk.page_num = $page_num

                            WITH chunk
                            MATCH (parent:Section {id: $parent_id})
                            SET parent.text = ""

                            WITH chunk, parent
                            MERGE (parent)-[:HAS_CHUNK]->(chunk)

                            RETURN chunk
                        """
                        with self.kg.session(database=Config.NEO4J_DATABASE) as session:
                            session.run(
                                create_chunk_cypher,
                                id=str(uuid.uuid4()),
                                level=level + 1,
                                title=title,
                                text=chunk,
                                page_num=page_num,
                                parent_id=parent_id,
                            )

    def create_chunk_node_for_law_section(self, text: str, page_num: int, parent_id: str, parent_hierarchy: str) -> None:
        for hierarchy in LawHierarchyType:
            query_all_law_section = f"""
                MATCH (section:{hierarchy.value[1]})
                RETURN section
            """

            with self.kg.session(database=Config.NEO4J_DATABASE) as session:
                all_law_sections = session.run(query_all_law_section)

                for record in all_law_sections:
                    parent = record["section"]
                    parent_id = parent["id"]
                    title = parent["title"]
                    text = parent["text"]
                    page_num = parent["page_num"]
                    hierarchy_type = parent["hierarchy_type"]

                    if len(text) > 15000:
                        text_splitter = CharacterTextSplitter.from_tiktoken_encoder(
                            encoding_name="cl100k_base", chunk_size=1000, chunk_overlap=100
                        )
                        chunk_list = text_splitter.split_text(text)
                        for chunk in chunk_list:
                            create_chunk_cypher = f"""
                                MERGE (chunk:Chunk {{id: $id}})
                                ON CREATE SET chunk.level = $level, hierarchy_type = $hierarchy_type, chunk.title = $title, chunk.text = $text, chunk.page_num = $page_num

                                WITH chunk
                                MATCH (parent:{hierarchy_type} {{id: $parent_id}})
                                SET parent.text = ""

                                WITH chunk, parent
                                MERGE (parent)-[:HAS_CHUNK]->(chunk)

                                RETURN chunk
                            """
                            with self.kg.session(database=Config.NEO4J_DATABASE) as session:
                                session.run(
                                    create_chunk_cypher,
                                    id=str(uuid.uuid4()),
                                    level=LawHierarchyType.chunk.value[0],
                                    hierarchy_type=LawHierarchyType.chunk.value[1],
                                    title="",  # title is not needed for chunk
                                    text=chunk,
                                    page_num=page_num,
                                    parent_id=parent_id,
                                )

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
    def set_document_node_for_law_section(self, law_section: LawSection) -> None:
        set_document_cypher = """
            MERGE (doc:Document {id: $id})
            SET doc.level = $level, doc.hierarchy_type = $hierarchy_type, doc.title = $title, doc.text = $text, doc.page_num = $page_num
            RETURN doc
        """
        with self.kg.session(database=Config.NEO4J_DATABASE) as session:
            session.run(
                set_document_cypher,
                id=str(law_section.id),
                level=LawHierarchyType.document.value[0],
                hierarchy_type=LawHierarchyType.document.value[1],
                title=law_section.title,
                text=law_section.text,
                page_num=law_section.page_num,
            )

    def set_section_node_for_law_section(self, law_section: LawSection) -> None:
        if law_section.parent and law_section.parent.hierarchy == LawHierarchyType.document:
            set_section_cypher = f"""
                MATCH (doc:Document {{id: $parent_id}})
                MERGE (section:{law_section.hierarchy.value[1]} {{id: $id}})
                SET section.level = $level, section.hierarchy_type = $hierarchy_type, section.title = $title, section.text = $text, section.page_num = $page_num
                MERGE (doc)-[:HAS_SECTION]->(section)
                RETURN section
            """
        elif law_section.parent and law_section.parent.hierarchy != LawHierarchyType.document:
            set_section_cypher = f"""
                MATCH (parent:{law_section.parent.hierarchy.value[1]} {{id: $parent_id}})
                MERGE (section:{law_section.hierarchy.value[1]} {{id: $id}})
                SET section.level = $level, section.hierarchy_type = $hierarchy_type, section.title = $title, section.text = $text, section.page_num = $page_num
                MERGE (parent)-[:HAS_SECTION]->(section)
                RETURN section
            """
        else:
            raise ValueError("Section must have a parent")

        with self.kg.session(database=Config.NEO4J_DATABASE) as session:
            session.run(
                set_section_cypher,
                parent_id=str(law_section.parent.id),
                id=str(law_section.id),
                level=law_section.hierarchy.value[0],
                hierarchy_type=law_section.hierarchy.value[1],
                title=law_section.title,
                text=law_section.text,
                page_num=law_section.page_num,
            )

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

    def set_section_node_for_section(self, section: Section) -> None:
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
