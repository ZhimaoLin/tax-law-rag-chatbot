from openai import OpenAI

from models.neo4j_db import Neo4jDB
from models.hierarchy_type import HierarchyType
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


def main():
    neo4j_db = Neo4jDB()
    openai_client = OpenAI()

    message_history = []
    system_message = """You are a professional Tax lawyer. You answer questions from your clients about tax laws. You only answer questions based on your knowledge base and the actual law. If you don't know the answer, you can say 'I don't know.'"""
    system_prompt = [{"role": "system", "content": system_message}]

    while True:
        print("=====================================")
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

        question = f"{context[-100000:]}\nUser: {question}"

        # Knowledge Base Search
        knowledge_base_list = []

        neo4j_vector_search = []

        for hierarchy in HierarchyType:
            result = neo4j_db.vector_search(question=question, label=hierarchy.value[1])
            if result:
                neo4j_vector_search.extend(result)

        neo4j_vector_search.sort(key=lambda x: x[0], reverse=True)

        neo4j_graph_search = []
        for result in neo4j_vector_search[:3]:
            id = result[1]
            hierarchy = result[3]
            # score = result[0]
            # level = result[2]
            # title = result[3]
            # text = result[4]
            # page_num = result[5]

            graph_search_result = neo4j_db.graph_search(query_id=id, label=hierarchy)

            for node in graph_search_result:
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

        knowledge_base = "\n".join(knowledge_base_list)

        user_message = f"""
            I need help with a tax question. Here is my question: {question}

            Please only answer the question based on the following knowledge base. I put the source path and page number below each source. If you think that source is useful for the answer, please attach the source path and page number to the answer at the end (it can be multiple sources and pages).
            {knowledge_base}

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

        print("=====================================")
        print(response)
        print("\n\n")


if __name__ == "__main__":
    main()
