"""Knowledge Base Creator"""

from knowledge_base import KnowledgeExtractor

from private_settings import PRIVATE_SETINGS

# Creating and running the knowledge base class based on the environment
if PRIVATE_SETINGS["LLM_LOCAL"]:
    ke = KnowledgeExtractor("ollama", "gpt-oss:20b", "mxbai-embed-large")
else:
    # Online
    ke = KnowledgeExtractor("openai", "gpt-4", "text-embedding-3-small")

ke.run(
    folder="Tomato recipes",
    file_name="rdf_graph",
    html_links=[
        "https://en.wikipedia.org/wiki/Tomato_sauce",
        "https://en.wikipedia.org/wiki/Pasta_al_pomodoro",
    ],
)
