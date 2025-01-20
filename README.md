# Tax Law Graph RAG Chatbot

An AI-powered tax lawyer/accountant that can answer tax related questions for clients. Behind the scene, there are 2 knowledge bases: a vector knowledge base using [Pinecone](https://www.pinecone.io/) and a graph knowledge base using [Neo4j](https://neo4j.com/). 

## Quick Demo



## Objectives

The main objective for this project is to experiment with Graph RAG and Vector-based RAG. According to the experimentation, Graph RAG can achieve higher accuracy than the vector-based RAG, however, it takes more time to traverse through the graph. 

### Real world use case

Leveraging Graph RAG can significantly enhance the efficiency of retrieving relevant information from extensive legal documents for lawyers. Also, the actual law is well structured, so that we can leverage the well defined structure and build the Graph Knowledge Base.

## PDF Parser

Throughout this project, plenty of time was spent on finding the best PDF parser even researching on the PDF encoding in order to enhance the quality of the input data. However, PDF is designed for visual representation instead of data extraction. This made PDF parsing inherently difficult. According to my experimentation, [PyMuPDF](https://pymupdf.readthedocs.io/en/latest/index.html) and [PyMuPDF4LLM](https://pymupdf.readthedocs.io/en/latest/pymupdf4llm/) offer me the best parsing result based on my use case. 

Here are some other PDF parse that you might consider:

- **pdfplumber**
  - Cannot handle multi-column PDFs. I need to manually detect the coordinate in order to parse the multi-column PDFs.
  - [https://github.com/jsvine/pdfplumber](https://github.com/jsvine/pdfplumber)
- **pdfminer.six’s**
  - It shines when reading the table of contents in the PDFs. If you want to parse the structure/outline of the PDFs, this package can help you.
  - https://pdfminersix.readthedocs.io/en/latest/index.html 
- **LayoutPDFReader**
  - This is the smartest pattern-based PDF parser. Without using any machine learning, it can meaningfully divide PDF into sections while overcoming the challenge of page break. However, it has issues with multi-column PDFs. 
  - [https://github.com/nlmatics/llmsherpa](https://github.com/nlmatics/llmsherpa)

## How to run the code?

### Environment variables

Create a `.env` file at the root directory. Then put the following keys:

- Neo4j
  - `neo4j=<Neo4j API Key>`
  - `NEO4J_URI=<Neo4j Graph DB URI>`
  - `NEO4J_USERNAME=<Neo4j Graph DB Username>`
  - `NEO4J_PASSWORD=<Neo4j Graph DB Password>`
  - `AURA_INSTANCEID=<Neo4j Graph DB Instance ID>`
  - `AURA_INSTANCENAME=<Neo4j Graph DB Instance Name>`
- OpenAI
  - `OPENAI_API_KEY=<OpenAI API Key>`
- Pinecone
  - `PINECONE_API_KEYS=<Pinecone API Key>`

Beside API keys, you can config the following in the `config.py`:

- Pinecone
  - `PINECONE_INDEX_NAME = "tax-law"`
- Neo4j vector embedding and index
  - `VECTOR_SOURCE_PROPERTY = "text"`
  - `VECTOR_EMBEDDING_PROPERTY = "text_embedding"`
- For text splitting
  - `TOKEN_ENCODING = "o200k_base"`
  - `CHUNK_SIZE = 1000`
  - `OVERLAP_SIZE = 200`

### Development environment

1. Windows 11 Pro Version `24H2`
2. Python `3.11.9`
3. VS Code

### Step 1: Install dependencies

Run 
```
pip install -r requirements.txt
```


### Step 2: Load data

#### Load CSV files

Change `CSV_FILE` to the path to your CSV file, and run

```
python ./load_csv.py
```

#### Load PDF files with table of contents

Change `PDF_PATH` to the path to your PDF file, which contains the table of contents, then run

```
python ./load_pdf_with_toc.py
```

#### Load PDF files without table of contents

Change `PDF_PATH` to the path to your PDF file, which does not contain the table of contents, then run

```
python ./load_pdf_without_toc.py
```

#### Load PDF files to vector storage

Change `PDF_PATH` to the path to your PDF file, then run

```
python ./load_vector_storage.py
```

### Step 3: Run chatbot

Run 
```
python ./chatbot.py
```

