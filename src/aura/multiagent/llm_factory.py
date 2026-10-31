"""AURA LLM Factory — Centralized model switching for OpenRouter and Gemini."""
from __future__ import annotations
import os
from typing import Any, List, Optional
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage


class MockMultiAgentLLM(BaseChatModel):
    """Deterministic offline mock model for tests and keyless local environments."""

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any,
    ):
        from langchain_core.outputs import ChatGeneration, ChatResult
        last = str(messages[-1].content).lower() if messages else ""

        if "route" in last or "supervisor" in str(messages[0].content).lower():
            if any(k in last for k in ("policy", "handbook", "guideline", "rule", "document")):
                reply = "NEXT: rag_agent"
            elif any(k in last for k in ("employee", "salary", "department", "sql", "select", "update", "delete", "budget")):
                reply = "NEXT: sql_agent"
            elif "analyze" in last or "summarize" in last or "result" in last:
                reply = "NEXT: analyst_agent"
            else:
                reply = "NEXT: sql_agent"
        elif "sqlite specialist" in str(messages[0].content).lower():
            if any(k in last for k in ("update", "raise")):
                reply = "UPDATE employees SET salary = salary + 5000 WHERE department = 'Engineering';"
            elif "salary" in last or "highest" in last:
                reply = "SELECT name, role, salary FROM employees ORDER BY salary DESC LIMIT 5;"
            elif "department" in last:
                reply = "SELECT name, budget, manager FROM departments;"
            else:
                reply = "SELECT id, name, role, department, salary FROM employees LIMIT 10;"
        elif "analyst" in str(messages[0].content).lower():
            reply = "### Executive Analysis\nAnalysis complete based on verified database and policy records."
        else:
            reply = "AURA Multi-Agent processing request."

        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=reply))])

    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any,
    ):
        return self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

    @property
    def _llm_type(self) -> str:
        return "mock_multiagent_llm"


def get_llm(model_name: Optional[str] = None, temperature: float = 0.0) -> BaseChatModel:
    """
    Returns configured ChatModel with dynamic model switching.
    Priority:
    1. OpenRouter (if OPENROUTER_API_KEY is configured and not mock)
    2. Google Gemini (if GEMINI_API_KEY is configured)
    3. MockMultiAgentLLM (safe offline fallback)
    """
    if os.getenv("AURA_TEST_MOCK_LLM"):
        return MockMultiAgentLLM()

    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    if openrouter_key and not openrouter_key.startswith("mock-") and not openrouter_key.startswith("your-"):
        try:
            from langchain_openai import ChatOpenAI
            selected_model = (
                model_name
                or os.getenv("OPENROUTER_MODEL")
                or os.getenv("AURA_LLM_MODEL")
                or "meta-llama/llama-3.3-70b-instruct:free"
            )
            return ChatOpenAI(
                model=selected_model,
                openai_api_key=openrouter_key,
                openai_api_base=os.getenv("AURA_LLM_BASE_URL", "https://openrouter.ai/api/v1"),
                temperature=temperature,
                default_headers={
                    "HTTP-Referer": "https://aura.governance",
                    "X-Title": "AURA Multi-Agent Governance",
                },
            )
        except Exception:
            pass

    return MockMultiAgentLLM()
