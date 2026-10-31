"""AURA Multi-Agent State definition for LangGraph."""
from __future__ import annotations
from typing import Annotated, Any, Dict, List, Optional
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class MultiAgentState(TypedDict):
    """Shared state passed between Supervisor and specialized sub-agents."""
    messages: Annotated[List[BaseMessage], add_messages]
    user_intent: str
    current_agent: str
    next_agent: str
    org_id: str
    user_role: str
    sql_query: Optional[str]
    sql_result: Optional[Any]
    rag_context: List[str]
    analysis_result: Optional[str]
    action_trace: List[Dict[str, Any]]
    final_output: Optional[str]
