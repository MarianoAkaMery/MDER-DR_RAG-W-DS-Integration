"""Knowledge Manager Module."""

# Standard library imports
import ast
import os
import re
from types import SimpleNamespace
import time
from itertools import permutations

# Third-party imports
import pandas as pd
from langchain_core.documents import Document
from langchain.embeddings import init_embeddings
from langchain_experimental.graph_transformers import LLMGraphTransformer
from sklearn.metrics.pairwise import cosine_similarity
from rdflib import Graph
from chromadb.api import ClientAPI
import chromadb
from chromadb.config import Settings
import joblib

# Local imports
from llm import LLMHandler
from .utils.graph_helpers import (
    process_name_or_relationship,
    normalize_l2,
    sparql_query,
    dataframe_to_text,
)
from .utils.graph_parameter import GRAPH_PARAMETER
from .utils.graph_prompt import (
    extract_triples,
    graph_prompt,
    translate_chunk,
    wrong_answer_prompt,
    update_triples,
)
from .utils.energenius_graph import EnergeniusGraph


class KnowledgeManager:
    """A class to manage knowledge base operations."""

    def __init__(
        self,
        provider: str,
        model: str,
        embedding: str,
        language: str,
        knowledge_base_path: str = "files",
    ):
        """Initialize the KnowledgeManager.

        Args:
            provider (str): Model provider.
            model (str): Model name.
            embedding (str): Embedding model name.
            language (str): Language used for responses.
            knowledge_base_path (str): Subfolder containing KB assets.
        """
        # Initialize the LLM handler used for prompt-based operations.
        self.llm_handler = LLMHandler(
            provider=provider,
            model=model,
            temperature=0.0,   # deterministic outputs
            language=None,     # language handled manually in pipeline
            keep_history=False # stateless requests
        )

        # Initialize embeddings backend for similarity search.
        self.embeddings = init_embeddings(
            model=embedding,
            provider=provider
        )

        # Save configuration.
        self.language = language
        self.knowledge_base_path = knowledge_base_path

        # Lazily loaded RDF graph object.
        self.graph = None


    def _update_entries(self, existing, new_entries):
        """Merge retrieval results by id, keeping smallest (best) distance.

        Args:
            existing (list[dict]): Current list with items shaped as:
                {"id": <str>, "distance": <float>}
            new_entries (list[dict]): New retrieval candidates.

        Returns:
            list[dict]: Merged/sorted list (ascending distance).
        """
        # Build a map for O(1) updates keyed by entity id.
        entry_map = {item["id"]: item for item in existing}

        # Merge incoming entries.
        for entry in new_entries:
            eid = entry["id"]
            dist = entry["distance"]

            if eid in entry_map:
                # If already present, keep the nearest distance.
                if dist < entry_map[eid]["distance"]:
                    entry_map[eid]["distance"] = dist
            else:
                # Insert unseen id.
                entry_map[eid] = {"id": eid, "distance": dist}

        # Convert map back to sorted list.
        updated_list = sorted(entry_map.values(), key=lambda x: x["distance"])
        return updated_list


    def user_message(self, message: str, answer_length: str) -> str:
        """
        Process a user message and return a response prompt/result.

        High-level flow:
        1. Load graph and vector database.
        2. Normalize/translate input (if needed).
        3. Extract question triples with LLM.
        4. Retrieve entities/chunks by embeddings.
        5. Build context and final prompt.
        6. Fallback retrieval if no triples/entities found.
        """

        # Resolve absolute path of KB data directory.
        self.path = os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "data",
            self.knowledge_base_path
        )
        rdf_path = os.path.join(self.path, "rdf_graph.ttl")

        if not os.path.exists(rdf_path):
            raise FileNotFoundError(
                f"Knowledge base not found: {rdf_path}. "
                "Build the KB first or select an existing one in the UI."
            )

        # Lazy-load RDF graph once per KnowledgeManager instance.
        if not self.graph:
            print("Loading graph...", end="")
            self.graph = EnergeniusGraph()
            self.graph.load_from_file(rdf_path)
            print("OK")

        # Initialize persistent Chroma client (vector DB).
        self.chromadbClient = chromadb.PersistentClient(
            path=os.path.join(self.path, "chroma_db"),
            settings=Settings(anonymized_telemetry=False),
        )

        print(f"\n\n-----User message-----\n{message}")

        # Early reject if prompt is too short.
        if len(message) < 3:
            return wrong_answer_prompt(self.language)

        # Translate user input to English when operating in other languages.
        if self.language != "English":
            message = self.llm_handler.generate_response(
                translate_chunk(), f"{message}", False
            )

        print(f"\n\n-----English user message-----\n{message}")

        # FOR MDER-DR
        question_triples = [] # Extract triples
        trps = self.llm_handler.generate_response(extract_triples(), f"{message}", False)
        pattern = r"\((.*?), (.*?), (.*?)\)"
        matches = re.findall(pattern, trps)
        print(f"\n\n-----GraphDocument from the question-----")
        for src_id, rel_id, tgt_id in matches:
            print(src_id, rel_id, tgt_id)
            question_triples.append(SimpleNamespace(
                source=SimpleNamespace(id=src_id.strip()),
                rel=SimpleNamespace(id=rel_id.strip()),
                target=SimpleNamespace(id=tgt_id.strip()),
            ))

        # Embed the question
        message_embedding = self.embeddings.embed_query(message)

        #####
        # Search similar entities
        #####

        # Load chromadb
        collection_entities = self.chromadbClient.get_or_create_collection(name="graph_entities", metadata={"hnsw:space":"cosine", "distance_function": "cosine"})
        collection_types = self.chromadbClient.get_or_create_collection(name="graph_types", metadata={"hnsw:space":"cosine", "distance_function": "cosine"})
        collection_descriptions = self.chromadbClient.get_or_create_collection(name="graph_descriptions", metadata={"hnsw:space":"cosine", "distance_function": "cosine"})
        collection_relationships = self.chromadbClient.get_or_create_collection(name="graph_relationships", metadata={"hnsw:space":"cosine", "distance_function": "cosine"})
        collection_triples = self.chromadbClient.get_or_create_collection(name="graph_triples", metadata={"hnsw:space":"cosine", "distance_function": "cosine"})
        collection_chunks = self.chromadbClient.get_or_create_collection(name="graph_chunks", metadata={"hnsw:space":"cosine", "distance_function": "cosine"})
        
        # Final output (or prompt) and assembled context.
        answer = ""
        context_data = ""

        # FOR MDER-DR
        while question_triples:
            all_entities = []

            # Process each extracted triple progressively.
            for rel_i in range(len(question_triples)):
                rel = question_triples[rel_i]
                
                # Syntactic deambiguation
                rel.source.id = process_name_or_relationship(rel.source.id)
                rel.rel.id = process_name_or_relationship(rel.rel.id)
                rel.target.id = process_name_or_relationship(rel.target.id)

                # Reason over past entities
                if all_entities: 
                    all_entity_descriptions_temp = self.graph.get_entity_descriptions(entities=[id["id"] for id in all_entities], distances=[id["distance"] for id in all_entities])
                    all_entity_descriptions_temp = dataframe_to_text(all_entity_descriptions_temp, context_name='')
                    input_trps = "\n".join([f"({rel.source.id}, {rel.rel.id}, {rel.target.id})" for rel in question_triples[:rel_i+1]])
                    trps = self.llm_handler.generate_response(update_triples(all_entity_descriptions_temp), f"{input_trps}", False)
                    
                    pattern = r"\((.*?), (.*?), (.*?)\)"
                    matches = re.findall(pattern, trps)
                    print(f"\n\n-----Reasoning on the triples-----")
                    for src_id, rel_id, tgt_id in matches:
                        print(src_id, rel_id, tgt_id)
                        rel.source.id = src_id
                        rel.rel.id = rel_id
                        rel.target.id = tgt_id
                    
                # --- Embeddings ---

                # Embedding
                rel.source.embedding = self.embeddings.embed_query(rel.source.id)
                rel.rel.embedding = self.embeddings.embed_query(rel.rel.id)
                rel.target.embedding = self.embeddings.embed_query(rel.target.id)

                # --- Source ---

                # Source types
                # NOTE: type-based filtering is currently disabled (kept as reference).
                """ source_types = collection_types.query(
                    query_embeddings=rel.source.properties["type_embedding"],
                    n_results=30,
                )
                source_types = [{"id": id, "distance": distance} for (id, distance) in zip(source_types["ids"][0], source_types["distances"][0]) if distance < 0.5] if source_types else []
                print(f"\n\n-----Types for {rel.source.type}-----")
                print("\n".join([f"{type}" for type in source_types])) """
                
                # Source entities
                #allowed_source_entities = self.graph.get_entities(types=[id["id"] for id in source_types])["entity"].to_list() if source_types else []
                #source_entities = collection_descriptions.query( # FOR MDER-DR
                source_entities = collection_entities.query( # FOR MDER-DR AND GRAPH-RAG
                    query_embeddings=rel.source.embedding,
                    #ids=[a for a in allowed_source_entities],
                    n_results=GRAPH_PARAMETER["TOP_ENTITIES"],
                )# if allowed_source_entities else []
                source_entities = [{"id": id, "distance": distance} for (id, distance) in zip(source_entities["ids"][0], source_entities["distances"][0]) if distance < GRAPH_PARAMETER["ENTITIES_DISTANCE_THRESHOLD"]] if source_entities else []
                print(f"\n\n-----Entities for {rel.source.id}-----")
                print("\n".join([f"{entity}" for entity in source_entities]))

                # Merge into global candidate list and cap size.
                all_entities = self._update_entries(all_entities, source_entities)
                all_entities = all_entities[:GRAPH_PARAMETER["MAXIMUM_ENTITIES"]]

            # Get entities
            if all_entities:

                all_entity_descriptions = self.graph.get_entity_descriptions(entities=[id["id"] for id in all_entities], distances=[id["distance"] for id in all_entities]) # FOR MDER-DR
                #all_entity_descriptions = self.graph.get_entity_chunks(entities=[id["id"] for id in all_entities], distances=[id["distance"] for id in all_entities]) # FOR GRAPH-RAG
                context_data += "\n" + dataframe_to_text(all_entity_descriptions, context_name='')

            # Augmentation step using vector-based retrieval
            chunks = collection_descriptions.query( # FOR MDER-DR
            #chunks = collection_entities.query( # FOR GRAPH-RAG
            #chunks = collection_chunks.query( # FOR VECTOR-RAG
                query_embeddings=message_embedding,
                n_results=GRAPH_PARAMETER["TOP_ENTITIES"],
            )
            chunks = [{"id": id, "distance": distance} for (id, distance) in zip(chunks["ids"][0], chunks["distances"][0]) if distance < GRAPH_PARAMETER["ENTITIES_DISTANCE_THRESHOLD"]] if chunks else []
            print(f"\n\n-----Chunks for {message}-----")
            print("\n".join([f"{chunk}" for chunk in chunks]))

            # Append chunk-like context if available
            if chunks:

                #chunks = self.graph.get_chunks(chunks=[id["id"] for id in chunks], distances=[id["distance"] for id in chunks]) # FOR VECTOR-RAG
                context_data += "\n\n" + dataframe_to_text(chunks, context_name='')

            # Build final graph-aware prompt from language, length, and context
            prompt = graph_prompt(self.language, answer_length, context_data)
            with open("prompt.txt", "w", encoding="utf-8") as f:
                f.write(prompt)

            answer = prompt
            break
                
                
        # No entities extracted from the question: fallback to only the question embedding
        while answer == "":
            
            # Search for the most similar entities based on the question
            entities = collection_descriptions.query( # FOR MDER-DR
            #entities = collection_entities.query( # FOR GRAPH-RAG
            #entities = collection_chunks.query( # FOR VECTOR-RAG
                query_embeddings=message_embedding,
                n_results=GRAPH_PARAMETER["TOP_ENTITIES_FALLBACK"],
            )
            entities = [{"id": id, "distance": distance} for (id, distance) in zip(entities["ids"][0], entities["distances"][0]) if distance < GRAPH_PARAMETER["ENTITIES_DISTANCE_THRESHOLD_FALLBACK"]] if entities else []
            print(f"\n\n-----Entitites for {message}-----")
            print("\n".join([f"{entity}" for entity in entities]))
        
            # No triple found: return wrong answer prompt
            if not entities:
                break

            # FOR GRAPH-RAG (disabled)
            """ # Get outgoing relationships
            allowed_source_entities_outgoing_relationships = self.graph.get_outgoing_relationships(entities=entities)["relationship"].to_list() if entities else []
            source_entities_outgoing_relationships = []
            for emb in [message_embedding]:
                res = collection_relationships.query(
                    query_embeddings=emb,
                    ids=[a for a in allowed_source_entities_outgoing_relationships],
                    n_results=10,
                ) if allowed_source_entities_outgoing_relationships else []
                source_entities_outgoing_relationships.extend([{"id": id, "distance": distance} for (id, distance) in zip(res["ids"][0], res["distances"][0]) if distance < 0.6] if res else [])
            print(f"\n\n-----Outgoing relationships-----")
            print("\n".join([f"{relationship}" for relationship in source_entities_outgoing_relationships]))
            
            # FOR GRAPH-RAG
            # 1-Hop target entities
            allowed_one_hop_target_entities = self.graph.get_triples(rel=[id["id"] for id in source_entities_outgoing_relationships], source=[id["id"] for id in entities])["target"].to_list() if source_entities_outgoing_relationships and entities else []
            one_hop_target_entities = []
            for emb in [message_embedding]:
                res = collection_entities.query(
                    query_embeddings=emb,
                    ids=[a for a in allowed_one_hop_target_entities],
                    n_results=5,
                ) if allowed_one_hop_target_entities else []
                one_hop_target_entities.extend([{"id": id, "distance": distance} for (id, distance) in zip(res["ids"][0], res["distances"][0]) if distance < 0.99] if res else [])
            print(f"\n\n-----1-hop Outgoing Entities-----")
            print("\n".join([f"{entity}" for entity in one_hop_target_entities]))

            # FOR GRAPH-RAG
            # Store in "all entities"
            entities = self._update_entries(entities, one_hop_target_entities)

            # FOR GRAPH-RAG
            # Get incoming relationships
            allowed_target_entities_incoming_relationships = self.graph.get_incoming_relationships(entities=entities)["relationship"].to_list() if entities else []
            target_entities_incoming_relationships = []
            for emb in [message_embedding]:
                res = collection_relationships.query(
                    query_embeddings=emb,
                    ids=[a for a in allowed_target_entities_incoming_relationships],
                    n_results=10,
                ) if allowed_target_entities_incoming_relationships else []
                target_entities_incoming_relationships.extend([{"id": id, "distance": distance} for (id, distance) in zip(res["ids"][0], res["distances"][0]) if distance < 0.6] if res else [])
            print(f"\n\n-----Incoming relationships-----")
            print("\n".join([f"{relationship}" for relationship in target_entities_incoming_relationships]))
            
            # FOR GRAPH-RAG
            # 1-Hop source entities
            allowed_one_hop_source_entities = self.graph.get_triples(rel=[id["id"] for id in target_entities_incoming_relationships], target=[id["id"] for id in entities])["source"].to_list() if target_entities_incoming_relationships and entities else []
            one_hop_source_entities = []
            for emb in [message_embedding]:
                res = collection_entities.query(
                    query_embeddings=emb,
                    ids=[a for a in allowed_one_hop_source_entities],
                    n_results=5,
                ) if allowed_one_hop_source_entities else []
                one_hop_source_entities.extend([{"id": id, "distance": distance} for (id, distance) in zip(res["ids"][0], res["distances"][0]) if distance < 0.99] if res else [])
            print(f"\n\n-----1-hop Incoming Entities-----")
            print("\n".join([f"{entity}" for entity in one_hop_source_entities]))

            # FOR GRAPH-RAG
            # Store in "all entities"
            entities = self._update_entries(entities, one_hop_source_entities) """
            
            # Build textual context from retrieved entity descriptions
            entity_descriptions = self.graph.get_entity_descriptions(entities=[id["id"] for id in entities], distances=[id["distance"] for id in entities]) # FOR MDER-DR
            #entity_descriptions = self.graph.get_entity_chunks(entities=[id["id"] for id in entities], distances=[id["distance"] for id in entities]) # FOR GRAPH-RAG
            #entity_descriptions = self.graph.get_chunks(chunks=[id["id"] for id in entities], distances=[id["distance"] for id in entities]) # FOR VECTOR-RAG
            context_data = dataframe_to_text(entity_descriptions, context_name='')

            # Build and persist final prompt
            prompt = graph_prompt(self.language, answer_length, context_data)
            with open("prompt.txt", "w", encoding="utf-8") as f:
                f.write(prompt)

            answer = prompt
            break
        
        # If both primary and fallback fail, return generic fallback response
        if answer == "":
            answer = wrong_answer_prompt(self.language)
            
        return answer

