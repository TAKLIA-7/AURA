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


import asyncio


class ChatGemini(BaseChatModel):
    """Google Gemini adapter for LangGraph multi-agent team."""
    model: str = "gemini-2.5-flash"
    api_key: str = ""

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any,
    ):
        import google.genai as genai
        from langchain_core.outputs import ChatGeneration, ChatResult
        client = genai.Client(api_key=self.api_key)
        contents = "\n".join(f"{m.type}: {m.content}" for m in messages)
        resp = client.models.generate_content(model=self.model, contents=contents)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=resp.text or ""))])

    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any,
    ):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: self._generate(messages, stop=stop, run_manager=run_manager, **kwargs))

    @property
    def _llm_type(self) -> str:
        return "chat_gemini"


MODELS = {
    "A": "bytedance-seed/seedream-4.5",
    "B": "anthropic/claude-haiku-4.5",
    "C": "tecent/hy3",
    "D": "deepseek/deepseek-chat",
    "gemini": "gemini-2.5-flash",
}


def resolve_model_name(key_or_name: Optional[str] = None) -> str:
    """Resolves a model alias (e.g. 'A', 'B', 'C', 'D', 'gemini') to its provider slug."""
    if not key_or_name:
        key_or_name = (
            os.getenv("AURA_MODEL")
            or os.getenv("MODEL")
            or os.getenv("OPENROUTER_MODEL")
            or os.getenv("AURA_LLM_MODEL")
            or "gemini"
        )
    return MODELS.get(key_or_name.strip(), key_or_name.strip())


def get_llm(model_name: Optional[str] = None, temperature: float = 0.0) -> BaseChatModel:
    """
    Returns configured ChatModel with dynamic model switching.
    Supports single-letter aliases: 'A', 'B', 'C', 'D', or full model slugs.
    Priority:
    1. Offline mock (if AURA_TEST_MOCK_LLM is set)
    2. Selected model resolved via MODELS dictionary
    3. Google Gemini direct client (if selected or default)
    4. OpenRouter ChatOpenAI (if OpenRouter key is provided)
    5. MockMultiAgentLLM fallback
    """
    if os.getenv("AURA_TEST_MOCK_LLM"):
        return MockMultiAgentLLM()

    resolved_model = resolve_model_name(model_name)
    provider = (os.getenv("AGENT_PROVIDER") or os.getenv("AURA_LLM_PROVIDER") or "").lower()
    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    openrouter_key = os.getenv("OPENROUTER_API_KEY")

    # 1. If explicit OpenRouter model is chosen (A, B, C, D, or slug with '/'), use OpenRouter
    is_openrouter_model = (
        resolved_model in (MODELS["A"], MODELS["B"], MODELS["C"], MODELS["D"])
        or ("/" in resolved_model and not resolved_model.startswith("gemini"))
        or provider == "openrouter"
    )

    if is_openrouter_model and not resolved_model.startswith("gemini") and openrouter_key:
        if not openrouter_key.startswith("mock-") and not openrouter_key.startswith("your-"):
            try:
                from langchain_openai import ChatOpenAI
                return ChatOpenAI(
                    model=resolved_model,
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

    # 2. If Gemini model is requested or Gemini provider
    if (resolved_model.startswith("gemini") or provider == "gemini") and gemini_key:
        try:
            selected_gemini = resolved_model if resolved_model.startswith("gemini") else (os.getenv("GEMINI_MODEL") or "gemini-2.5-flash")
            return ChatGemini(api_key=gemini_key, model=selected_gemini)
        except Exception:
            pass

    # 3. Fallback to Gemini if key exists
    if gemini_key:
        try:
            return ChatGemini(api_key=gemini_key, model="gemini-2.5-flash")
        except Exception:
            pass


    return MockMultiAgentLLM()

