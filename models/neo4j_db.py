from langchain_text_splitters import CharacterTextSplitter
from neo4j import GraphDatabase
import tiktoken
import uuid

from config import Config
from models.section import Section
from models.hierarchy_type import HierarchyType


class Neo4jDB:
    def __init__(self):
        kg = GraphDatabase.driver(Config.NEO4J_URI, auth=(Config.NEO4J_USERNAME, Config.NEO4J_PASSWORD))
        kg.verify_connectivity()
        self.kg = kg

    # region Split Text
    def create_chunk_node(self) -> None:
        text_splitter = CharacterTextSplitter.from_tiktoken_encoder(
            encoding_name=Config.TOKEN_ENCODING,
            chunk_size=Config.CHUNK_SIZE,
            chunk_overlap=Config.OVERLAP_SIZE,
        )
        encoder = tiktoken.get_encoding("o200k_base")

        for hierarchy in HierarchyType:
            query_all_law_section = f"""
                MATCH (section:{hierarchy.value[1]})
                RETURN section
            """

            with self.kg.session(database=Config.NEO4J_DATABASE) as session:
                all_law_sections = session.run(query_all_law_section)

                for record in all_law_sections:
                    parent = record["section"]
                    parent_id = parent["id"]
                    text = parent["text"]
                    page_num = parent["page_num"]
                    hierarchy = parent["hierarchy"]

                    tokens = encoder.encode(text)
                    if len(tokens) >= 5000:
                        chunk_list = text_splitter.split_text(text)
                        for chunk in chunk_list:
                            create_chunk_cypher = f"""
                                MERGE (chunk:Chunk {{id: $id}})
                                ON CREATE SET chunk.level = $level, chunk.hierarchy = $hierarchy, chunk.title = $title, chunk.text = $text, chunk.page_num = $page_num

                                WITH chunk
                                MATCH (parent:{hierarchy} {{id: $parent_id}})
                                SET parent.text = ""

                                WITH chunk, parent
                                MERGE (parent)-[:HAS_CHUNK]->(chunk)

                                RETURN chunk
                            """
                            with self.kg.session(database=Config.NEO4J_DATABASE) as session:
                                session.run(
                                    create_chunk_cypher,
                                    id=str(uuid.uuid4()),
                                    level=HierarchyType.chunk.value[0],
                                    hierarchy=HierarchyType.chunk.value[1],
                                    title="",  # title is not needed for chunk
                                    text=chunk,
                                    page_num=page_num,
                                    parent_id=parent_id,
                                )

    # endregion

    # region Add Nodes
    def set_document_node(self, law_section: Section) -> None:
        set_document_cypher = """
            MERGE (doc:Document {id: $id})
            SET doc.level = $level, doc.hierarchy = $hierarchy, doc.title = $title, doc.text = $text, doc.page_num = $page_num
            RETURN doc
        """
        with self.kg.session(database=Config.NEO4J_DATABASE) as session:
            session.run(
                set_document_cypher,
                id=str(law_section.id),
                level=HierarchyType.document.value[0],
                hierarchy=HierarchyType.document.value[1],
                title=law_section.title,
                text=law_section.text,
                page_num=law_section.page_num,
            )

    def set_section_node(self, section: Section) -> None:
        if section.parent and section.parent.hierarchy == HierarchyType.document:
            set_section_cypher = f"""
                MATCH (doc:Document {{id: $parent_id}})
                MERGE (section:{section.hierarchy.value[1]} {{id: $id}})
                SET section.level = $level, section.hierarchy = $hierarchy, section.title = $title, section.text = $text, section.page_num = $page_num
                MERGE (doc)-[:HAS_SECTION]->(section)
                RETURN section
            """
        elif section.parent and section.parent.level > 0:
            set_section_cypher = f"""
                MATCH (parent:{section.parent.hierarchy.value[1]} {{id: $parent_id}})
                MERGE (section:{section.hierarchy.value[1]} {{id: $id}})
                SET section.level = $level, section.hierarchy = $hierarchy, section.title = $title, section.text = $text, section.page_num = $page_num
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
                hierarchy=section.hierarchy.value[1],
                title=section.title,
                text=section.text,
                page_num=section.page_num,
            )

    # endregion

    # region Embedding
    def add_embedding(self, label: str):
        add_embedding_cypher = f"""
            MATCH (section:{label})
            WITH section, genai.vector.encode(
                CASE
                    WHEN section.text IS NOT NULL AND section.text <> '' THEN section.text
                    WHEN section.title IS NOT NULL AND section.title <> '' THEN section.title
                    ELSE ' '
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

    # region Search
    def vector_search(self, question: str, label: str) -> list[tuple[float, str, str, str, int]]:
        search_result_list = []
        vector_search_query = """
            WITH genai.vector.encode($question, 'OpenAI', {token: $openai_key}) AS question_embedding
            CALL db.index.vector.queryNodes($index_name, $top_k, question_embedding) YIELD node, score
            RETURN score, node.id, node.level, node.hierarchy, node.title, node.text, node.page_num
        """

        with self.kg.session(database=Config.NEO4J_DATABASE) as session:
            search_result_list = []
            index_name = f"index_{label}"

            result = session.run(
                vector_search_query,
                question=question,
                openai_key=Config.OPENAI_API_KEY,
                index_name=index_name,
                top_k=2,
            )
            for node in result:
                score = node[0]
                id = node[1]
                level = node[2]
                hierarchy = node[3]
                title = node[4]
                text = node[5]
                page_num = node[6]

                search_result_list.append((score, id, level, hierarchy, title, text, page_num))

        search_result_list.sort(key=lambda x: x[0], reverse=True)
        return search_result_list

    def search_path(self, query_id: str, label: str) -> list[Section]:
        graph_search_query = f"""
            MATCH p = (doc:Document)-[*]->(node:{label} {{id: $id}})
            RETURN nodes(p) AS all_nodes
        """

        with self.kg.session(database=Config.NEO4J_DATABASE) as session:
            result = session.run(graph_search_query, id=str(query_id))
            for record in result:
                path = [self.__convert_neo4j_node_to_section(node) for node in record["all_nodes"]]
                path.sort(key=lambda x: x.level)
                return path
        return []

    def graph_search(self, query_id: str, label: str) -> list[Section]:
        graph_search_query = f"""
            MATCH p = (node:{label} {{id: $id}})-[*]->(end)
            RETURN nodes(p) AS all_nodes
        """

        with self.kg.session(database=Config.NEO4J_DATABASE) as session:
            result = session.run(graph_search_query, id=str(query_id))
            for record in result:
                return [self.__convert_neo4j_node_to_section(node) for node in record["all_nodes"]]
        return []

    # endregion

    def __convert_neo4j_node_to_section(self, node: dict) -> Section:
        id = node["id"]
        title = node["title"]
        level = node["level"]
        hierarchy = HierarchyType.check_hierarchy_type(title)
        text = node["text"]
        page_num = node["page_num"]
        return Section(
            id=id,
            level=level,
            hierarchy=hierarchy,
            title=title,
            text=text,
            page_num=page_num,
        )
