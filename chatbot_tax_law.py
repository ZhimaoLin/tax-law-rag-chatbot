# from langchain_neo4j import GraphCypherQAChain
# from langchain_neo4j import Neo4jGraph
# from langchain_community.vectorstores import Neo4jVector
# from langchain.prompts.prompt import PromptTemplate
# from langchain_openai import ChatOpenAI, OpenAIEmbeddings
# from langchain_openai import OpenAIEmbeddings
from uuid import UUID
from neo4j import Driver, GraphDatabase
from openai import OpenAI


from config import Config
from models.tax_law.law_hierarchy import LawHierarchyType
from models.tax_law.law_section import LawSection


class VectorSearchResult(LawSection):
    score: float


def connect_neo4j_db() -> None:
    kg = GraphDatabase.driver(Config.NEO4J_URI, auth=(Config.NEO4J_USERNAME, Config.NEO4J_PASSWORD))
    kg.verify_connectivity()
    return kg


def neo4j_vector_search(question: str, kg: Driver) -> list[VectorSearchResult]:
    search_result_list = []
    vector_search_query = """
        WITH genai.vector.encode($question, 'OpenAI', {token: $openai_key}) AS question_embedding
        CALL db.index.vector.queryNodes($index_name, $top_k, question_embedding) YIELD node, score
        RETURN score, node.id, node.level, node.title, node.text, node.page_num
    """

    with kg.session(database=Config.NEO4J_DATABASE) as session:
        for hierarchy in LawHierarchyType:
            index_name = f"index_{hierarchy.value[1]}"

            result = session.run(
                vector_search_query,
                question=question,
                openai_key=Config.OPENAI_API_KEY,
                index_name=index_name,
                top_k=2,
            )
            for node in result:
                search_result = VectorSearchResult(
                    score=node[0],
                    id=node[1],
                    level=node[2],
                    title=node[3],
                    text=node[4],
                    page_num=node[5],
                    hierarchy=hierarchy,
                )
                search_result_list.append(search_result)

    search_result_list.sort(key=lambda x: x.score, reverse=True)
    return search_result_list


def neo4j_graph_search(node: VectorSearchResult, kg: Driver) -> list[LawSection]:
    search_result_list = []

    graph_search_query = f"""
        MATCH p = (node:{node.hierarchy.value[1]} {{id: $id}})-[*]->(end)
        WITH nodes(p) AS all_nodes
        UNWIND all_nodes AS target_node
        RETURN
            target_node.id AS id,
            target_node.level AS level,
            target_node.title AS title,
            target_node.text AS text,
            target_node.page_num AS page_num
    """

    with kg.session(database=Config.NEO4J_DATABASE) as session:
        result = session.run(graph_search_query, id=str(node.id))
        for node in result:
            search_result = LawSection(
                id=node[0],
                level=node[1],
                title=node[2],
                text=node[3],
                page_num=node[4],
                hierarchy=LawHierarchyType.check_hierarchy_type(node[2]),
            )
            search_result_list.append(search_result)
    return search_result_list


def main():
    kg = connect_neo4j_db()
    openai_client = OpenAI()

    message_history = []
    system_message = """You are a professional Tax lawyer. You answer questions from your clients about tax laws. You only answer questions based on your knowledge base and the actual law. If you don't know the answer, you can say 'I don't know.'"""
    system_prompt = [{"role": "system", "content": system_message}]

    while True:
        print("=====================================")
        question = input("Enter a question or type 'exit' to quit: ")
        if question.lower() == "exit":
            return

        context_list = []
        for message in message_history:
            if message["role"] == "user":
                context_list.append(f"User: {message['content']}")
            elif message["role"] == "assistant":
                context_list.append(f"Assistant: {message['content']}")
        context = "\n".join(context_list)

        question = f"{context}\nUser: {question}"

        knowledge_base_list = []

        # Knowledge Base Search
        vector_search = neo4j_vector_search(question, kg)
        for result in vector_search[:5]:
            graph_search = neo4j_graph_search(result, kg)

            for section in graph_search:
                knowledge_base_list.append(section.text)

        knowledge_base = "\n".join(knowledge_base_list)

        user_message = f"""
            I need help with a tax question. Here is my question: {question}

            Please only answer the question based on the following knowledge base:
            {knowledge_base}

            If you don't know the answer, you can say 'I don't know.'
        """
        message_history.append({"role": "user", "content": user_message})

        completion = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=system_prompt + message_history,
            temperature=0,
        )

        response = completion.choices[0].message.content
        message_history.append({"role": "assistant", "content": response})

        print("=====================================")
        print(response)
        print("\n\n")


main()


# enhanced_graph = Neo4jGraph(
#     url=Config.NEO4J_URI,
#     username=Config.NEO4J_USERNAME,
#     password=Config.NEO4J_PASSWORD,
#     database=Config.NEO4J_DATABASE,
#     enhanced_schema=True,
# )


# neo4j_vector_store = Neo4jVector.from_existing_graph(
#     embedding=OpenAIEmbeddings(),
#     url=Config.NEO4J_URI,
#     username=Config.NEO4J_USERNAME,
#     password=Config.NEO4J_PASSWORD,
#     index_name="index_Section",
#     node_label="Section",
#     text_node_properties=Config.VECTOR_SOURCE_PROPERTY,
#     embedding_node_property=Config.VECTOR_EMBEDDING_PROPERTY,
# )

# retriever = neo4j_vector_store.as_retriever()

# chain = RetrievalQAWithSourcesChain.from_chain_type(
#     ChatOpenAI(temperature=0),
#     chain_type="stuff",
#     retriever=retriever
# )

# cypher_prompt = """
# You are a Neo4j Cypher developer. Based on my question search the relevant node using the vector index. Also find the neighbor nodes along the path. Retrieve the information in the `text` property of the nodes.

# Here is the schema information:
# - Node label: `Title`, `Subtitle`, `Chapter`, `Subchapter`, `Part`, `Section`, `SectionL1`, `SectionL2`, `SectionL3`, `SectionL4`
# - Relationship: `Title`-[:HAS_SECTION]->`Subtitle`-[:HAS_SECTION]->`Chapter`-[:HAS_SECTION]->`Subchapter`-[:HAS_SECTION]->`Part`-[:HAS_SECTION]->`Section`-[:HAS_SECTION]->`SectionL1`-[:HAS_SECTION]->`SectionL2`-[:HAS_SECTION]->`SectionL3`-[:HAS_SECTION]->`SectionL4`

# You don't have ID information. Just query through the keywords in the question.
# """

# CYPHER_GENERATION_PROMPT = PromptTemplate(
#     input_variables=["schema", "question"],
#     template=cypher_prompt
# )

# llm = ChatOpenAI(model="gpt-4o", temperature=0)
# chain = GraphCypherQAChain.from_llm(graph=enhanced_graph, llm=llm, cypher_prompt=CYPHER_GENERATION_PROMPT, verbose=True, allow_dangerous_requests=True)
# response = chain.invoke({"query": "How is the final tax rounded?"})
# print(response)
