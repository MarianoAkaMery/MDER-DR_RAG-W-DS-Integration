
import re
import copy
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from tqdm import tqdm


class Disambiguator:

    def __init__(self, graph_documents, embedding_function, llm_call, max_iter=5):

        self.embedding_function = embedding_function
        self.llm_call = llm_call

        self.max_iter = max_iter

        self.graph_documents = graph_documents
        self.all_entities = {}


    def run(self):

        self.extract_valid_entities_from_triples()
        
        self.cycle()

        self.update_original_triples()

        return self.graph_documents


    def cycle(self):
        
        for i in range(self.max_iter):
            print(f"Cycle {i}")
            all_entities_temp = self.group_similar_nodes()
            if all_entities_temp == self.all_entities:
                break
            self.all_entities = copy.deepcopy(all_entities_temp)


    def group_similar_nodes(self):

        if len(self.all_entities) <= 1:
            return copy.deepcopy(self.all_entities)

        keys = list(self.all_entities.keys())
        names = [value[0] for value in self.all_entities.values()]
        types = [value[1] for value in self.all_entities.values()]
        names_types = [f"{value[0]} ({value[1]})" for value in self.all_entities.values()]
        page_contents = [value[2] for value in self.all_entities.values()]
        embeddings = np.array([self.embedding_function(name_type) for name_type in names_types])
        similarity_matrix = cosine_similarity(embeddings)

        all_entities_temp = copy.deepcopy(self.all_entities)

        for i in tqdm(range(len(keys)), desc="Disambiguation: "):
            for j in range(i + 1, len(keys)):
                if similarity_matrix[i][j] > 0.85 and not names_types[i] == names_types[j] and not self.are_connected(names[i], types[i], names[j], types[j]) and not self.is_alias(names[i], types[i], names[j], types[j]) and not self.contains_number(names[i], types[i], names[j], types[j]):
                    print(f"{keys[i]} ({names_types[i]}) - {keys[j]} ({names_types[j]})")
                    same = None
                    while same not in {"SAME", "DIFFERENT"}:
                        same = self.llm_call(
                            self.compare_entities_prompt(page_contents[i] if page_contents[i] == page_contents[j] else f"{page_contents[i]}\n{page_contents[j]}"),
                            f"{names_types[i]}\n{names_types[j]}", False)
                    
                    if same == "SAME":
                        new_entity_name = self.llm_call(
                            self.select_new_entity_name_prompt(page_contents[i] if page_contents[i] == page_contents[j] else f"{page_contents[i]}\n{page_contents[j]}"),
                            f"{names[i]}\n{names[j]}", False)
                        print(f"{keys[i]} ({names[i]}) - {keys[j]} ({names[j]}) -> {new_entity_name}")
                        all_entities_temp[keys[i]][0] = new_entity_name
                        all_entities_temp[keys[j]][0] = new_entity_name
        
        return all_entities_temp
    

    def extract_valid_entities_from_triples(self):
        # For each chunk
        for i, graph_doc in enumerate(self.graph_documents):
            # For each triple
            for j, triple in enumerate(graph_doc.relationships):
                if not self.is_valid_triple(triple):
                    continue
                self.all_entities[triple.source.id] = [triple.source.id, triple.source.type, graph_doc.source.page_content]
                self.all_entities[triple.target.id] = [triple.target.id, triple.target.type, graph_doc.source.page_content]
    

    def update_original_triples(self):
        for graph_doc in self.graph_documents:
            updated_relationships = []
            for triple in graph_doc.relationships:
                # Keep triple only if both source and target are in all_entities
                if triple.source.id in self.all_entities and triple.target.id in self.all_entities:
                    # Update source.id
                    triple.source.id = self.all_entities[triple.source.id][0]
                    # Update target.id
                    triple.target.id = self.all_entities[triple.target.id][0]
                    updated_relationships.append(triple)
            # Replace relationships with filtered list
            graph_doc.relationships = updated_relationships

    

    def are_connected(self, name1, type1, name2, type2):
        for graph_doc in self.graph_documents:
            for triple in graph_doc.relationships:

                # If a triple that connects the two nodes exists
                if triple.source.id == name1 and triple.source.type == type1 and triple.target.id == name2 and triple.target.type == type2:
                    return True
                if triple.source.id == name2 and triple.source.type == type2 and triple.target.id == name1 and triple.target.type == type1:
                    return True
                
        return False
    

    def is_alias(self, name1, type1, name2, type2):
        if any([("alias" in s.lower()) for s in [name1, type1, name2, type2]]):
            return False
        else:
            return False
    

    def contains_number(self, name1, type1, name2, type2):
        if any([(re.search(r'\d', s) ) for s in [name1, type1, name2, type2]]):
            return True
        else:
            return False


    def is_valid_triple(self, triple):
        # Check the validity of all the elements
        return (
            self.is_valid_text(triple.source.id) and
            self.is_valid_text(triple.source.type) and
            self.is_valid_text(triple.type) and
            self.is_valid_text(triple.target.id) and
            self.is_valid_text(triple.target.type)
        )


    def is_valid_text(self, text: str) -> bool:
        # Match any non-empty string that contains at least one alphanumeric character
        if not re.match(r'^(?=.*[a-zA-Z0-9]).+$', text):
            return False
        # Length check to avoid very long entity names
        if len(re.split(r'[ _]+', text)) > 5:
            return False
        else:
            return True
        

    def compare_entities_prompt(self, context) -> str:
        return f"""
---Role---
You are a system that determines whether two given entities represent the same concept or item.

---Goal---
Return "SAME" if the entities refer to the same concept, even if they differ in grammatical number, formatting, or minor variations (e.g., "Deduction" vs "Deductions", "Microwave" vs "Microwaves").
Return "DIFFERENT" if the entities differ in meaning, quantity, time span, or any other substantive attribute (e.g., "6H day" vs "8H day", "1 March 31 December" vs "1 March 15 December").
Focus on core meaning, not surface form.

---Context---
{context}

---Output---
Plain text only: either "SAME" or "DIFFERENT" with no formatting, commentary, or explanation.
        """
    

    def select_new_entity_name_prompt(self, context) -> str:
        return f"""
---Role---
You are a system that selects the most representative name between two given entities.

---Goal---
Return the entity name that best represents the shared concept between the two inputs.
If both refer to the same concept, choose the version that is:
- Singular (not plural)
- Shorter in length
- More general or canonical
If the entities differ in meaning, return the one that is more representative or commonly used.
If neither entity name is sufficiently representative, you may select a different name that is not among the two inputs, as long as it best captures the shared concept and is expressed in English.

---Context---
{context}

---Output---
Plain text only: the selected entity name with no formatting, commentary, or explanation.
        """
