"""AURA Multi-Agent LangGraph Assembly."""
from __future__ import annotations
from typing import Literal, Optional
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from aura.multiagent.state import MultiAgentState
from aura.multiagent.agents import SpecializedAgents
from aura.sdk.interceptor import AuraGovernor


def build_multiagent_graph(governor: Optional[AuraGovernor] = None, model_name: Optional[str] = None):
    """Constructs and compiles the governed multi-agent LangGraph workflow."""
    agents = SpecializedAgents(governor=governor, model_name=model_name)
    workflow = StateGraph(MultiAgentState)

    # 1. Add Agent Nodes
    workflow.add_node("supervisor", agents.supervisor_node)
    workflow.add_node("sql_agent", agents.sql_agent_node)
    workflow.add_node("rag_agent", agents.rag_agent_node)
    workflow.add_node("analyst_agent", agents.analyst_agent_node)

    # 2. Add Edges & Conditional Routing
    workflow.add_edge(START, "supervisor")

    def route_supervisor(state: MultiAgentState) -> Literal["sql_agent", "rag_agent", "analyst_agent", "__end__"]:
        target = state.get("next_agent", "FINISH")
        if target == "sql_agent":
            return "sql_agent"
        elif target == "rag_agent":
            return "rag_agent"
        elif target == "analyst_agent":
            return "analyst_agent"
        return END

    workflow.add_conditional_edges("supervisor", route_supervisor)

    def route_specialist(state: MultiAgentState) -> Literal["analyst_agent", "supervisor", "__end__"]:
        next_step = state.get("next_agent")
        if next_step == "analyst_agent":
            return "analyst_agent"
        elif next_step == "FINISH":
            return END
        return "supervisor"

    workflow.add_conditional_edges("sql_agent", route_specialist)
    workflow.add_conditional_edges("rag_agent", route_specialist)
    workflow.add_conditional_edges("analyst_agent", lambda state: END)

    checkpointer = MemorySaver()
    return workflow.compile(checkpointer=checkpointer)
