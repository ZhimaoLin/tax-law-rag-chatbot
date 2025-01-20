from openai import OpenAI

from models.neo4j_db import Neo4jDB
from models.hierarchy_type import HierarchyType
from models.pinecone_db import PineconeDB
from models.section import Section


class GraphSearchResult(Section):
    path: list[Section]

    def __str__(self) -> str:
        source = []
        for section in self.path:
            source.append(section.title)

        return f"""
            Title: {self.title}
            Text: {self.text}
            Page Number: {self.page_num}
            Source: {" -> ".join(source)}
        """


def get_pinecone_knowledge_base(question: str, openai_client: OpenAI, pinecone_db: PineconeDB) -> str:
    response = openai_client.embeddings.create(input=question, model="text-embedding-3-large")
    question_embedding = response.data[0].embedding
    result = pinecone_db.query(query_embedding=question_embedding, top_k=3)

    knowledge_base_list = []
    for chunk in result:
        text = chunk["metadata"]["text"]
        page_num = chunk["metadata"]["page_num"]
        knowledge_base_list.append(f"Text: {text}\nPage Number: {page_num}")

    return "\n".join(knowledge_base_list)


def get_neo4j_knowledge_base(question: str, neo4j_db: Neo4jDB) -> str:
    knowledge_base_list = []
    neo4j_vector_search = []
    neo4j_graph_search = []

    for hierarchy in HierarchyType:
        result = neo4j_db.vector_search(question=question, label=hierarchy.value[1])
        if result:
            neo4j_vector_search.extend(result)
    neo4j_vector_search.sort(key=lambda x: x[0], reverse=True)

    for result in neo4j_vector_search[:3]:
        # score = result[0]
        id = result[1]
        level = result[2]
        hierarchy = result[3]
        title = result[4]
        text = result[5]
        page_num = result[6]

        graph_search_result_temp = []
        graph_search_result_temp.append(
            Section(
                id=id,
                level=level,
                hierarchy=HierarchyType.check_hierarchy_type(title),
                title=title,
                text=text,
                page_num=page_num,
            )
        )

        result_temp = neo4j_db.graph_search(query_id=id, label=hierarchy)
        graph_search_result_temp.extend(result_temp)

        for node in graph_search_result_temp:
            path = neo4j_db.search_path(query_id=node.id, label=node.hierarchy.value[1])

            neo4j_graph_search.append(
                GraphSearchResult(
                    id=node.id,
                    level=node.level,
                    hierarchy=node.hierarchy,
                    title=node.title,
                    text=node.text,
                    page_num=node.page_num,
                    path=path,
                )
            )

    for result in neo4j_graph_search:
        knowledge_base_list.append(str(result))

    return "\n".join(knowledge_base_list)


def main():
    neo4j_db = Neo4jDB()
    pinecone_db = PineconeDB()
    openai_client = OpenAI()

    message_history = []
    system_message = """You are a professional Tax lawyer and an accountant dealing with Tax. You answer questions from your valuable clients about tax. You only answer questions based on your knowledge base and the actual law. If you don't know the answer, you can say 'I don't know.'"""
    system_prompt = [{"role": "system", "content": system_message}]

    while True:
        print("==========================================================================")
        question = input("Enter a question or type 'exit' to quit: ")
        question = "How is the tax imposed for married couples?"
        if question.lower() == "exit":
            return

        context_list = []
        for message in message_history:
            if message["role"] == "user":
                context_list.append(f"User: {message['content']}")
            elif message["role"] == "assistant":
                context_list.append(f"Assistant: {message['content']}")
        context = "\n".join(context_list)

        question = f"{context[-200000:]}\nUser: {question}"

        pinecone_knowledge = get_pinecone_knowledge_base(
            question=question, openai_client=openai_client, pinecone_db=pinecone_db
        )

        neo4j_knowledge = get_neo4j_knowledge_base(question=question, neo4j_db=neo4j_db)

        user_message = f"""
            I need help with a tax question. Here is my question: {question}

            Please only answer the question based on the following knowledge base. I put the source path and page number below each source. If you think that source is useful for the answer, please attach the source path and page number to the answer at the end (it can be multiple sources and pages).
            {neo4j_knowledge}
            {pinecone_knowledge}

            Attach the source path and page number at the end of your answer if you think it is useful.
            If you do not have enough reliable source from the knowledge base, just leave the source part blank. Do not make up any information.
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

        print("==========================================================================")
        print(response)
        print("\n\n")


if __name__ == "__main__":
    main()
