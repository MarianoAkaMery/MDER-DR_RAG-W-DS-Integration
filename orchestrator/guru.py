"""Guru class for orchestrating the workflow of the application."""

from langchain_core.messages import BaseMessage

from knowledge_base import KnowledgeManager
from llm import LLMHandler
from .static_calculations import (
    calculate_gas_to_hvac_savings,
    extract_savings_inputs,
    should_calculate_gas_to_hvac_savings,
)


class Guru:
    """Guru class for orchestrating the workflow of the application.

    This class is responsible for managing the flow of the application,
    including loading configurations, initializing components, and
    orchestrating the execution of tasks.
    """

    def __init__(self, provider: str, model: str, embedding: str, language: str,
                 temperature: float, answer_length: str, knowledge_base: str, use_knowledge: bool = True) -> None:
        """_Initialize the Guru class._"""
        self.llm = LLMHandler(
            provider=provider,
            model=model,
            temperature=temperature,
            language=language,
            keep_history=True
        )
        self.know_base = KnowledgeManager(
            provider=provider,
            model=model,
            embedding=embedding,
            language=language,
            knowledge_base_path=f"files_{knowledge_base}"
        )
        self.use_knowledge = use_knowledge
        self.answer_length = answer_length
        self.knowledge_base = knowledge_base
        self.language = language

    def _run_static_calculation(self, message: str) -> str | None:
        if not should_calculate_gas_to_hvac_savings(message):
            return None
        inputs = extract_savings_inputs(message)
        return calculate_gas_to_hvac_savings(self.language, inputs)

    def load_past_messages(self, messages: list[BaseMessage]) -> None:
        """
        Load past messages into the orchestrator.
        Args:
            messages (list[BaseMessage]): List of past messages to load.
        """
        self.llm.load_messages(messages)

    def user_message(self, message: str):# -> str:
        """
        Process a user message and return a response.
        Args:
            message (str): The user message to process.
        Returns:
            str: The response from the LLM.
        """
        llm_only = f"""
---Role---
You answer questions. Respond in {self.language}.

---Goal---
Give a direct answer in {self.language}.
If unsure, say you don’t know. Never invent information.

---Target response length and format---
Reply EXTREMELY BRIEFLY in {self.language}.
Provide only the answer.
        """
        static_response = self._run_static_calculation(message)
        if static_response is not None:
            return static_response
        if self.use_knowledge:
            return self.llm.generate_response(self.know_base.user_message(message, self.answer_length), message, False)
        else:
            return self.llm.generate_response(llm_only, message, use_past_history=False)

    def user_message_stream(self, message: str):# -> str:
        """
        Process a user message and return a response.
        Args:
            message (str): The user message to process.
        Returns:
            str: The response from the LLM.
        """
        llm_only = f"""
---Role---
You answer questions. Respond in {self.language}.

---Goal---
Give a direct answer in {self.language}.
If unsure, say you don’t know. Never invent information.

---Target response length and format---
Reply EXTREMELY BRIEFLY in {self.language}.
Provide only the answer.
        """
        static_response = self._run_static_calculation(message)
        if static_response is not None:
            yield static_response
        elif self.use_knowledge:
            yield from self.llm.generate_response_stream(self.know_base.user_message(message, self.answer_length), message, False)
        else:
            yield from self.llm.generate_response_stream(llm_only, message, use_past_history=False)
        
    def set_language(self, language: str) -> None:
        self.know_base.language = language
        self.llm.set_language(language)
        
    def set_knowledge_base(self, knowledge_base: str) -> None:
        self.knowledge_base = knowledge_base
        self.know_base.knowledge_base_path = f"files_{knowledge_base}"
        
    def set_temperature(self, temperature: float) -> None:
        self.temperature = temperature
        
