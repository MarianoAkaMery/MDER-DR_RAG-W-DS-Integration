"""Knowledge Base Creator"""

from knowledge_base import KnowledgeExtractor

from private_settings import PRIVATE_SETINGS

# Creating and running the knowledge base class based on the environment
if PRIVATE_SETINGS["LLM_LOCAL"]:
    ke = KnowledgeExtractor("ollama", "llama3.2", "mxbai-embed-large")
else:
    # Online
    ke = KnowledgeExtractor("openai", "gpt-4", "text-embedding-3-small")

ke.run(
    knowledge_base="Tomato_recipes",
    html_links=[
        "https://en.wikipedia.org/wiki/Tomato_sauce",
        "https://en.wikipedia.org/wiki/Pasta_al_pomodoro",
    ],
)
