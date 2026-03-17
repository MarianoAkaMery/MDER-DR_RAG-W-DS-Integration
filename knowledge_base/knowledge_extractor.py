"""Module to create a knowledge base from a text files."""

# Standard library
import hashlib
import os
import re
import io

# Third-party
import joblib
import numpy as np
import requests
import chromadb
from chromadb.config import Settings
from tqdm import tqdm
from bs4 import BeautifulSoup
from pdfminer.high_level import extract_text_to_fp
from pdfminer.layout import LAParams
from sklearn.metrics.pairwise import cosine_similarity
from rdflib import FOAF, OWL, RDF, RDFS, XSD, BNode, Graph, Literal, Namespace, URIRef

# LangChain
from langchain.embeddings import init_embeddings
from langchain_community.document_loaders import AsyncHtmlLoader, PyPDFLoader
from langchain_community.document_transformers import Html2TextTransformer
from langchain_core.documents import Document
from langchain_experimental.graph_transformers import LLMGraphTransformer
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_experimental.text_splitter import SemanticChunker

# Local
from llm import LLMHandler
from .utils.graph_prompt import (
    extract_descriptions_for_entities,
    extract_descriptions_for_triples,
    translate_chunk,
    summarize_chunk,
)
from .utils.graph_helpers import process_name_or_relationship, normalize_l2, sparql_query
from .utils.energenius_graph import EnergeniusGraph
from .utils.disambiguator import Disambiguator
from itertools import permutations


class KnowledgeExtractor:
    """_Class to create a knowledge base from a text files._"""

    def __init__(self, provider: str, model: str, embedding: str):
        """_Initialize the KnowledgeExtractor._

        Args:
            provider (str): _Description of the model provider._
            model (str): _Description of the model name._
            embedding (str): _Description of the embedding model name._
        """
        # LLM wrapper used for translation/summarization/extraction prompts.
        self.llm_handler = LLMHandler(
            provider=provider, model=model, temperature=0.0, language=None, keep_history=False
        )

        # Embedding backend used in chunking/disambiguation/indexing.
        self.embeddings = init_embeddings(model=embedding, provider=provider)

        # Transformer that converts text chunks into graph-style relations.
        self.llm_graph_transformer = LLMGraphTransformer(
            llm=self.llm_handler.get_model(),
            #node_properties=True,
            #relationship_properties=True,
            #ignore_tool_usage=True,
            additional_instructions="""Ensure that:
- No detail is omitted, even if implicit or inferred
- Compound or nested relationships are captured
- Temporal, causal, or hierarchical links are included (e.g., Crime And Punishment (1998 Film) produces Crime And Punishment HAS_YEAR 1988)
- Synonyms or aliases are noted if present (e.g., Cornelia "Lia" Melis produces Cornelia Melis HAS_ALIAS Lia)
- Types are noted and correctly separed from the entity names (e.g., Crime And Punishment (Film) produces Crime And Punishment as entity name and Film as type)
- Prefer short and concise node and relationship names instead of keeping names (e.g., Crime and Punishment (Spanish: Crimen y castigo) produces Crime and Punishment HAS_SPANISH_TITLE Crimen y castigo)
- Do not merge multi-word entities into single tokens (e.g., prefer Class A instead of ClassA)""",
        )


    
    def run(
        self,
        file_name: str,
        folder: str = "files",
        html_links: list[str] = None,
        documents: list[dict] = None,
        load_cached_docs: bool = False,
        load_cached_preprocessed_chunks: bool = False,
        load_cached_graph_documents: bool = False,
        load_cached_graph_documents_disambigued: bool = False,
        load_cached_triple_descriptions: bool = False,
        load_cached_entity_descriptions: bool = False,
        load_cached_embeddings: bool = False,
    ) -> None:
        """_Main function to create the knowledge base._"""

        # Base data path for this KB run.
        dir_path = os.path.dirname(os.path.realpath(__file__))
        path = os.path.join(dir_path, "data", folder)

        # Checking if files folder is present
        if not os.path.exists(path):
            os.makedirs(path)

        # --- Download documents ---
        
        # If documents provided as texts
        if not documents:

            if load_cached_docs:
                try:
                    print("Trying to load existing raw_docs.joblib")
                    raw_docs = joblib.load(os.path.join(path, "raw_docs.joblib"))  # Load
                except FileNotFoundError:
                    print("No existing knowledge base found.")
                    return
            else:
                    
                # Separate HTML and PDF links
                html_urls = []
                pdf_urls = []

                for url in html_links:
                    if url.lower().endswith('.pdf'):
                        pdf_urls.append(url)
                    else:
                        html_urls.append(url)

                raw_docs = []

                # Load HTML documents
                if html_urls:
                    html_loader = AsyncHtmlLoader(html_urls) # this works using requests
                    raw_docs.extend(html_loader.load())

                # Load PDF documents and convert to HTML
                for pdf_url in pdf_urls:
                    try:
                        # Download PDF from URL
                        response = requests.get(pdf_url, timeout=30)
                        response.raise_for_status()

                        # Extract text with layout preservation as HTML
                        output_string = io.StringIO()
                        pdf_file = io.BytesIO(response.content)

                        extract_text_to_fp(
                            pdf_file, 
                            output_string, 
                            laparams=LAParams(),
                            output_type='html',  # Get HTML output
                            codec=None
                        )

                        # Get the HTML content
                        html_content = output_string.getvalue()

                        # Parse and convert spans to headings
                        html_content = convert_spans_to_headings(html_content)

                        # Create a Document object similar to HTML loader output
                        pdf_document = Document(
                            page_content=html_content,
                            metadata={
                                "source": pdf_url,
                            }
                        )
                        raw_docs.append(pdf_document)

                    except Exception as e:
                        print(f"Error loading PDF from {pdf_url}: {e}")
                        continue

                joblib.dump(raw_docs, os.path.join(path, "raw_docs.joblib")) # Save
            
        else: # If documents are provided in form of text
            
            raw_docs = []
            for doc in documents:
                raw_docs.append(
                    Document(
                        page_content=doc["content"],
                        metadata={
                            "source": doc["title"],
                            "language": "en",
                        }
                    )
                )


        # --- Process documents ---

        # Strip html tags
        processed_docs = raw_docs
        for doc in processed_docs:
            doc.page_content = extract_main_content(doc.page_content)
        #chunks = processed_docs

        # Semantic chunker
        chunker = SemanticChunker(
            embeddings=self.embeddings,
            sentence_split_regex=r"(?<=[.!?|])\s+",
            breakpoint_threshold_type='standard_deviation', breakpoint_threshold_amount=2,
            min_chunk_size=100,
        )
        chunks = chunker.split_documents(processed_docs)
        
        # Size limiter 1
        size_limiter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=0,
            length_function=len,
            separators=["|"], # |<h1>
        )
        temp_chunks = []
        for chunk in chunks:
            limited_chunks = size_limiter.split_text(chunk.page_content)
            # Grouping small chunks
            for i, _ in enumerate(limited_chunks):
                if len(limited_chunks[i]) <= 99 and i < len(limited_chunks)-1:
                    limited_chunks[i] = f"{limited_chunks[i]}\n{limited_chunks[i+1]}"
                    del limited_chunks[i]
            # Final chunks list
            for text in limited_chunks:
                temp_chunks.append(chunk.model_copy(update={"page_content": text}))
        chunks = temp_chunks
        
        # Size limiter 2
        size_limiter = RecursiveCharacterTextSplitter(
            chunk_size=1500,
            chunk_overlap=0,
            length_function=len,
            separators=[".", "!", "?"],
        )
        temp_chunks = []
        for chunk in chunks:
            limited_chunks = size_limiter.split_text(chunk.page_content)
            # Grouping small chunks
            for i, _ in enumerate(limited_chunks):
                if len(limited_chunks[i]) <= 99 and i < len(limited_chunks)-1:
                    limited_chunks[i] = f"{limited_chunks[i]}\n{limited_chunks[i+1]}"
                    del limited_chunks[i]
            # Final chunks list
            for text in limited_chunks:
                temp_chunks.append(chunk.model_copy(update={"page_content": text}))
        chunks = temp_chunks

        print(f"> Number of documents: {len(processed_docs)}")
        print(f"> Number of chunks: {len(chunks)}")
        #print("\n\n\n".join([str(chunk) for chunk in chunks]))


        # --- LLM pre-processing ---

        if load_cached_preprocessed_chunks:
            try:
                print("Trying to load existing preprocessed_chunks.joblib")
                preprocessed_chunks = joblib.load(os.path.join(path, "preprocessed_chunks.joblib"))  # Load
            except FileNotFoundError:
                print("No existing knowledge base found.")
                return
        else:
            preprocessed_chunks = chunks
            
            for i in tqdm(range(len(preprocessed_chunks)), desc="Translation & summarization of the chunks: "):

                if "language" not in preprocessed_chunks[i].metadata.keys():
                    preprocessed_chunks[i].metadata["language"] = "na"
                    
                # Translation
                if "en" not in preprocessed_chunks[i].metadata["language"].lower():
                    preprocessed_chunks[i].page_content = strip_quotes(
                        self.llm_handler.generate_response(translate_chunk(), f"{preprocessed_chunks[i].page_content}", False)
                    )

                # Summarization
                prev = preprocessed_chunks[i - 1].page_content if i > 0 and preprocessed_chunks[i - 1].metadata["source"] == preprocessed_chunks[i].metadata["source"] else ""
                curr = preprocessed_chunks[i].page_content
                next_ = preprocessed_chunks[i + 1].page_content if i < len(preprocessed_chunks) - 1 and preprocessed_chunks[i + 1].metadata["source"] == preprocessed_chunks[i].metadata["source"] else ""
                context = "\n".join(filter(None, [
                    prev if prev else None, #self._get_last_sentence(prev) if prev else None,
                    curr,
                    next_ if next_ else None, #self._get_first_sentence(next_) if next_ else None
                ]))
                #print(f"\n\n{context}")
                preprocessed_chunks[i].page_content = strip_quotes(
                    self.llm_handler.generate_response(summarize_chunk(context), curr, False)
                ).replace("\n\n", "\n")

            joblib.dump(preprocessed_chunks, os.path.join(path, "preprocessed_chunks.joblib")) # Save


        # --- LLM conversion to graph documents ---

        if load_cached_graph_documents:
            try:
                print("Trying to load existing graph_documents.joblib")
                graph_documents = joblib.load(os.path.join(path, "graph_documents.joblib"))  # Load
            except FileNotFoundError:
                print("No existing knowledge base found.")
                return
        else:
            
            graph_documents = []
            for doc in tqdm(preprocessed_chunks, desc="Conversion to graph documents: "): # Nodes and relationships extraction
                graph_from_chunk = self.llm_graph_transformer.convert_to_graph_documents([doc])[0]
                print("\n".join([f"{rel.source.id} ({rel.source.type}), {rel.type}, {rel.target.id} ({rel.target.type})" for rel in graph_from_chunk.relationships]))
                graph_documents.append(graph_from_chunk)
                
            joblib.dump(graph_documents, os.path.join(path, "graph_documents.joblib")) # Save


        # --- Disambiguation ---

        if load_cached_graph_documents_disambigued:
            try:
                print("Trying to load existing graph_documents_disambigued.joblib")
                graph_documents_disambigued = joblib.load(os.path.join(path, "graph_documents_disambigued.joblib"))  # Load
            except FileNotFoundError:
                print("No existing knowledge base found.")
                return
        else:
            
            syn = Disambiguator(graph_documents, self.embeddings.embed_query, self.llm_handler.generate_response)
            graph_documents_disambigued = syn.run()
                
            joblib.dump(graph_documents_disambigued, os.path.join(path, "graph_documents_disambigued.joblib")) # Save
        

        # --- Store in the KG ---

        # Initialize RDF Graph
        graph = EnergeniusGraph()
        graph.load_ontology()

        # For each unique "full document"
        for i, graph_doc_unique_source in enumerate(tqdm({doc.source.metadata["source"] for doc in graph_documents}, desc="RDF graph creation: ")):

            # Document
            doc_id = remove_non_alphanumerical(graph_doc_unique_source)
            doc_uri = graph.DATA[f"Document_{doc_id}"]
            graph.rdf_graph.add((doc_uri, RDF.type, graph.ONTO.Document))
            graph.rdf_graph.add((doc_uri, graph.ONTO.hasUri, Literal(doc_id, datatype=XSD.string)))
            
            # For each chunk in this "full document" -> filter chunks from "graph document"
            filtered_chunks = [doc_chunk for doc_chunk in graph_documents if doc_chunk.source.metadata["source"] == graph_doc_unique_source]
            for j, chunk in enumerate(filtered_chunks):
                
                # Chunk
                doc_id = remove_non_alphanumerical(chunk.source.metadata["source"])
                doc_uri = graph.DATA[f"Document_{doc_id}"]
                chunk_uri = graph.DATA[f"Chunk_{doc_id}_{j}"]
                graph.rdf_graph.add((chunk_uri, RDF.type, graph.ONTO.Chunk))
                graph.rdf_graph.add((chunk_uri, graph.ONTO.hasUri, Literal(chunk_uri, datatype=XSD.string)))
                graph.rdf_graph.add((chunk_uri, graph.ONTO.hasContent, Literal(chunk.source.page_content, datatype=XSD.string)))

                graph.rdf_graph.add((doc_uri, graph.ONTO.hasChunk, chunk_uri))
                graph.rdf_graph.add((chunk_uri, graph.ONTO.belongsToDocument, doc_uri))

                if j > 0:
                    previous_chunk_uri = graph.DATA[f"Chunk_{doc_id}_{j-1}"]
                    graph.rdf_graph.add((previous_chunk_uri, graph.ONTO.hasNext, chunk_uri))
                    graph.rdf_graph.add((chunk_uri, graph.ONTO.hasPrevious, previous_chunk_uri))

                # Entities and relationships
                for k, rel in enumerate(chunk.relationships):

                    # Source entity
                    source_entity_id = remove_non_alphanumerical(rel.source.id)
                    source_entity_uri = graph.DATA[f"Entity_{source_entity_id}"]
                    graph.rdf_graph.add((source_entity_uri, RDF.type, graph.ONTO.Entity))
                    graph.rdf_graph.add((source_entity_uri, graph.ONTO.hasName, Literal(rel.source.id, datatype=XSD.string)))
                    
                    source_entity_type_id = remove_non_alphanumerical(rel.source.type)
                    source_entity_type_uri = graph.DATA[f"EntityType_{source_entity_type_id}"]
                    graph.rdf_graph.add((source_entity_type_uri, RDF.type, graph.ONTO.EntityType))
                    graph.rdf_graph.add((source_entity_type_uri, graph.ONTO.hasName, Literal(rel.source.type, datatype=XSD.string)))
                    
                    graph.rdf_graph.add((source_entity_uri, graph.ONTO.hasType, source_entity_type_uri))
                    graph.rdf_graph.add((source_entity_type_uri, graph.ONTO.isTypeOf, source_entity_uri))

                    graph.rdf_graph.add((chunk_uri, graph.ONTO.hasEntity, source_entity_uri))
                    graph.rdf_graph.add((doc_uri, graph.ONTO.hasEntity, source_entity_uri))

                    graph.rdf_graph.add((source_entity_uri, graph.ONTO.belongsToChunk, chunk_uri))
                    graph.rdf_graph.add((source_entity_uri, graph.ONTO.belongsToDocument, doc_uri))

                    graph.rdf_graph.add((source_entity_type_uri, graph.ONTO.belongsToChunk, chunk_uri))
                    graph.rdf_graph.add((source_entity_type_uri, graph.ONTO.belongsToDocument, doc_uri))

                    # Target entity
                    target_entity_id = remove_non_alphanumerical(rel.target.id)
                    target_entity_uri = graph.DATA[f"Entity_{target_entity_id}"]
                    graph.rdf_graph.add((target_entity_uri, RDF.type, graph.ONTO.Entity))
                    graph.rdf_graph.add((target_entity_uri, graph.ONTO.hasName, Literal(rel.target.id, datatype=XSD.string)))
                    
                    target_entity_type_id = remove_non_alphanumerical(rel.target.type)
                    target_entity_type_uri = graph.DATA[f"EntityType_{target_entity_type_id}"]
                    graph.rdf_graph.add((target_entity_type_uri, RDF.type, graph.ONTO.EntityType))
                    graph.rdf_graph.add((target_entity_type_uri, graph.ONTO.hasName, Literal(rel.target.type, datatype=XSD.string)))
                    
                    graph.rdf_graph.add((target_entity_uri, graph.ONTO.hasType, target_entity_type_uri))
                    graph.rdf_graph.add((target_entity_type_uri, graph.ONTO.isTypeOf, target_entity_uri))

                    graph.rdf_graph.add((chunk_uri, graph.ONTO.hasEntity, target_entity_uri))
                    graph.rdf_graph.add((doc_uri, graph.ONTO.hasEntity, target_entity_uri))

                    graph.rdf_graph.add((target_entity_uri, graph.ONTO.belongsToChunk, chunk_uri))
                    graph.rdf_graph.add((target_entity_uri, graph.ONTO.belongsToDocument, doc_uri))

                    graph.rdf_graph.add((target_entity_type_uri, graph.ONTO.belongsToChunk, chunk_uri))
                    graph.rdf_graph.add((target_entity_type_uri, graph.ONTO.belongsToDocument, doc_uri))
                
                    # Relationship
                    rel_id = remove_non_alphanumerical(rel.type)
                    rel_uri = graph.DATA[f"Relationship_{rel_id}"]
                    graph.rdf_graph.add((rel_uri, RDF.type, graph.ONTO.Relationship))
                    graph.rdf_graph.add((rel_uri, graph.ONTO.hasName, Literal(rel.type, datatype=XSD.string)))
                    
                    graph.rdf_graph.add((rel_uri, graph.ONTO.hasSource, source_entity_uri))
                    graph.rdf_graph.add((source_entity_uri, graph.ONTO.isSourceOf, rel_uri))

                    graph.rdf_graph.add((rel_uri, graph.ONTO.hasTarget, target_entity_uri))
                    graph.rdf_graph.add((target_entity_uri, graph.ONTO.isTargetOf, rel_uri))

                    graph.rdf_graph.add((source_entity_uri, graph.ONTO.relatesTarget, target_entity_uri))
                    graph.rdf_graph.add((target_entity_uri, graph.ONTO.relatesSource, source_entity_uri))

                    # Triples
                    #bnode = BNode()
                    bnode_uri = graph.DATA[f"Triple_{source_entity_id}_{rel_id}_{target_entity_id}"]
                    graph.rdf_graph.add((bnode_uri, RDF.type, graph.ONTO.Triple))
                    graph.rdf_graph.add((bnode_uri, graph.ONTO.hasSource, source_entity_uri))
                    graph.rdf_graph.add((bnode_uri, graph.ONTO.hasRelationship, rel_uri))
                    graph.rdf_graph.add((bnode_uri, graph.ONTO.hasTarget, target_entity_uri))
                    graph.rdf_graph.add((bnode_uri, graph.ONTO.belongsToChunk, chunk_uri))
                    
                    graph.rdf_graph.add((source_entity_uri, graph.ONTO.composes, bnode_uri))
                    graph.rdf_graph.add((rel_uri, graph.ONTO.composes, bnode_uri))
                    graph.rdf_graph.add((target_entity_uri, graph.ONTO.composes, bnode_uri))

                    graph.rdf_graph.add((chunk_uri, graph.ONTO.hasRelationship, rel_uri))
                    graph.rdf_graph.add((doc_uri, graph.ONTO.hasRelationship, rel_uri))

                    graph.rdf_graph.add((rel_uri, graph.ONTO.belongsToChunk, chunk_uri))
                    graph.rdf_graph.add((rel_uri, graph.ONTO.belongsToDocument, doc_uri))

        graph.save_to_file(os.path.join(path, f"{file_name}_no_descriptions.ttl")) # Save

        # --- Triple descriptions ---
        # Triple Context Restoration (TCR) and Query-Driven Feedback (QF)

        if load_cached_triple_descriptions:
            try:
                print("Trying to load existing rdf_graph_triple_descriptions.ttl")
                # Re-initialize RDF Graph
                graph = EnergeniusGraph()
                graph.load_ontology()
                graph.load_from_file(os.path.join(path, f"{file_name}_triple_descriptions.ttl")) # Load
            except FileNotFoundError:
                print("No existing knowledge base found.")
                return
        else:
            
            triples = graph.get_triples_and_chunks()
            
            triples["prev_chunk_content"] = triples["prev_chunk_content"].fillna("").str.replace("\n\n", " ").replace("\n", " ")
            triples["chunk_content"] = triples["chunk_content"].fillna("").str.replace("\n\n", " ").replace("\n", " ")
            triples["next_chunk_content"] = triples["next_chunk_content"].fillna("").str.replace("\n\n", " ").replace("\n", " ")

            for index, row in tqdm(list(triples.iterrows()), desc="Summarizing triples: "):

                chunk = f"{row['prev_chunk_content']}\n{row['chunk_content']}\n{row['next_chunk_content']}"
                
                description = strip_quotes(
                    self.llm_handler.generate_response(
                        extract_descriptions_for_triples(f"{chunk}"), f"{row['source_entity_name']} {row['relationship_name']} {row['target_entity_name']}", False)
                ).replace("\n\n", " ").replace("\n", " ")
                graph.rdf_graph.add((row["triple"], graph.ONTO.hasDescription, Literal(description, datatype=XSD.string)))
            
            graph.save_to_file(os.path.join(path, f"{file_name}_triple_descriptions.ttl")) # Save


        # --- Entity descriptions ---

        if load_cached_entity_descriptions:
            try:
                print("Trying to load existing rdf_graph.ttl")
                # Re-initialize RDF Graph
                graph = EnergeniusGraph()
                graph.load_ontology()
                graph.load_from_file(os.path.join(path, f"{file_name}.ttl")) # Load
            except FileNotFoundError:
                print("No existing knowledge base found.")
                return
        else:

            # Entities
            entities = graph.get_entities()
            for index, row in tqdm(list(entities.iterrows()), desc="Summarizing entities: "):

                # Types
                types = graph.get_types(row["entity"])
                entity_description_from_triples = '\n'.join(f'{row["name"]} is {type["name"]}.' for _, type in types.iterrows())
                
                # Descriptions
                entity_description_from_triples += "\n" + "\n".join(graph.get_entity_triples(row["entity"])["description"])
                print(entity_description_from_triples)
                description = strip_quotes(
                    self.llm_handler.generate_response(
                        extract_descriptions_for_entities(f"{entity_description_from_triples}"), f"{row['name']}", False)
                ).replace("\n\n", " ").replace("\n", " ")
                graph.rdf_graph.add((row["entity"], graph.ONTO.hasDescription, Literal(description, datatype=XSD.string)))

            graph.save_to_file(os.path.join(path, f"{file_name}.ttl")) # Save
        
        
        # --- Embeddings ---

        client = chromadb.PersistentClient(
            path=os.path.join(path, "chroma_db"),
            settings=Settings(anonymized_telemetry=False),
        )
        collection_entities = client.get_or_create_collection(name="graph_entities", metadata={"hnsw:space":"cosine", "distance_function": "cosine"})
        collection_types = client.get_or_create_collection(name="graph_types", metadata={"hnsw:space":"cosine", "distance_function": "cosine"})
        collection_descriptions = client.get_or_create_collection(name="graph_descriptions", metadata={"hnsw:space":"cosine", "distance_function": "cosine"})
        collection_relationships = client.get_or_create_collection(name="graph_relationships", metadata={"hnsw:space":"cosine", "distance_function": "cosine"})
        collection_triples = client.get_or_create_collection(name="graph_triples", metadata={"hnsw:space":"cosine", "distance_function": "cosine"})
        collection_chunks = client.get_or_create_collection(name="graph_chunks", metadata={"hnsw:space":"cosine", "distance_function": "cosine"})

        if not load_cached_embeddings:

            # Entities
            #collection_entities.delete(ids=collection_entities.get()["ids"])
            entities = graph.get_entities()
            for index, row in tqdm(list(entities.iterrows()), desc="Embedding entities: "):
                emb = self.embeddings.embed_query(row["name"])
                collection_entities.add(ids=[row["entity"]], embeddings=[emb])
                if len(row["description"]) > 1500:
                    row["description"] = row["description"][:1500] + "..."
                emb_desc = self.embeddings.embed_query(row["description"])
                collection_descriptions.add(ids=[row["entity"]], embeddings=[emb_desc])

            # Types
            #collection_types.delete(ids=collection_types.get()["ids"])
            types = graph.get_types()
            for index, row in tqdm(list(types.iterrows()), desc="Embedding types: "):
                emb = self.embeddings.embed_query(row["name"])
                collection_types.add(ids=[row["type"]], embeddings=[emb])

            # Relationships
            #collection_relationships.delete(ids=collection_relationships.get()["ids"])
            relationships = graph.get_relationships()
            for index, row in tqdm(list(relationships.iterrows()), desc="Embedding relationships: "):
                emb = self.embeddings.embed_query(row["name"])
                collection_relationships.add(ids=[row["relationship"]], embeddings=[emb])

            # Triples
            #collection_triples.delete(ids=collection_triples.get()["ids"])
            triples = graph.get_triples()
            for index, row in tqdm(list(triples.iterrows()), desc="Embedding triples: "):
                if len(row["description"]) > 1500:
                    row["description"] = row["description"][:1500] + "..."
                emb = self.embeddings.embed_query(row["description"])
                collection_triples.add(ids=[row["triple"]], embeddings=[emb])

            # Chunks
            #collection_chunks.delete(ids=collection_chunks.get()["ids"])
            chunks = graph.get_chunks()
            for index, row in tqdm(list(chunks.iterrows()), desc="Embedding chunks: "):
                if len(row["content"]) > 1500:
                    row["content"] = row["content"][:1500] + "..."
                emb = self.embeddings.embed_query(row["content"])
                collection_chunks.add(ids=[row["chunk"]], embeddings=[emb])

        return
    


# Helper functions

def remove_non_alphanumerical(s: str, hash: bool = True) -> str:
    """Sanitize string for URI-safe ids; optional md5 suffix for uniqueness."""
    strin = re.sub("[^A-Za-z0-9]", "_", s)
    h = hashlib.md5(s.encode()).hexdigest()
    return strin + "_" + h if hash else strin

def strip_quotes(s):
    """Remove matching wrapping single/double quotes from a string."""
    return s[1:-1] if s and s[0] == s[-1] and s[0] in ('"', "'") else s


def get_last_sentence(text):
    """Return last sentence if long enough, otherwise empty."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    sentences
    return sentences[-1] if sentences and len(sentences[-1].strip()) >= 4 else ""


def get_first_sentence(text):
    """Return first sentence from text."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return sentences[0] if sentences else ""


def extract_main_content(html):
    """Extract main content from HTML by trying common article selectors."""
    # Alternative route kept for reference:
    # return Html2TextTransformer().transform_documents(html_docs)

    soup = BeautifulSoup(html, "html.parser")

    # Remove obvious non-content elements first.
    for tag in soup.find_all(["header", "footer", "nav", "aside", "form", "script", "style"]):
        tag.decompose()
    for tag in soup.find_all(attrs={"aria-hidden": "true"}):
        tag.decompose()

    # Common selectors where article content is usually located.
    candidates = [
        ("main", {}),
        ("div", {"id": "content"}),
        ("div", {"id": "main-content"}),
        ("div", {"id": "main"}),
        ("div", {"id": "article-content"}),
        ("div", {"id": "page-content"}),
        ("div", {"id": "primary"}),
        ("div", {"id": "post"}),
        ("div", {"class": "content"}),
        ("div", {"class": "main-content"}),
        ("div", {"class": "article-content"}),
        ("div", {"class": "post-content"}),
        ("div", {"class": "post"}),
        ("div", {"class": "entry-content"}),
        ("div", {"class": "page-content"}),
        ("div", {"class": "blog-post"}),
        ("div", {"class": "story"}),
        ("section", {"class": "content"}),
        ("section", {"id": "content"}),
        ("section", {"class": "main-content"}),
        ("section", {"id": "main-content"}),
        ("section", {"class": "article"}),
        ("section", {"id": "article"}),
        ("section", {}),
    ]

    # Try selectors in order and return first useful extraction.
    for tag, attrs in candidates:
        matches = soup.find_all(tag, attrs=attrs)
        if matches:
            return "\n\n".join(
                BeautifulSoup(
                    re.sub(r"(?i)<(h[1-6]\b[^>]*)>", r"|<\1>", str(match)),
                    "html.parser",
                )
                .get_text(separator="\n", strip=True)
                .replace("||", "|")
                for match in matches
            )

    # Fallback: plain text from entire page.
    return soup.get_text(separator="\n", strip=True)


def extract_font_size(style):
    """Extract integer px font-size from inline style string."""
    match = re.search(r"font-size:(\d+)px", style)
    return int(match.group(1)) if match else None


def convert_spans_to_headings(html_content):
    """Promote large-font spans into semantic headings for better chunking."""
    soup = BeautifulSoup(html_content, "html.parser")

    for span in soup.find_all("span"):
        style = span.get("style", "")
        font_size = extract_font_size(style)
        if font_size is not None:
            if font_size >= 26:
                tag = "h1"
            elif 22 <= font_size < 26:
                tag = "h2"
            elif 18 <= font_size < 22:
                tag = "h3"
            else:
                continue

            new_tag = soup.new_tag(tag)
            new_tag.string = span.get_text()
            span.replace_with(new_tag)

    return str(soup)

        

# Disambiguation helper functions

def is_valid_text(text: str) -> bool:
    """Check if text contains alphanumeric characters and <= 5 words."""
    if not re.match(r"^(?=.*[a-zA-Z0-9]).+$", text):
        return False
    return len(re.split(r"[ _]+", text)) <= 5


def normalize_entity(entity: str, processor) -> str | None:
    """Normalize an entity and return None if result is invalid."""
    processed = processor(entity)
    return processed if re.match(r"^(?=.*[a-zA-Z0-9]).+$", processed) else None


def to_keep(s1: str, s2: str) -> str:
    """Pick representative string between two equivalent entities."""
    s1c, s2c = s1.count(" "), s2.count(" ")
    if s1c > s2c and s1c < 5:
        return s1
    elif s2c > s1c and s2c < 5:
        return s2
    return s1 if len(s1) <= len(s2) else s2
