"""AURA Multi-Agent Specialized Agents with Strict Governance Interception."""
from __future__ import annotations
import json
from typing import Any, Dict, List, Optional
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from aura.multiagent.state import MultiAgentState
from aura.multiagent.llm_factory import get_llm
from aura.sdk.interceptor import AuraGovernor


class SpecializedAgents:
    """Specialized agents coordinated by the Supervisor. All tool execution routes through AuraGovernor."""

    def __init__(self, governor: Optional[AuraGovernor] = None) -> None:
        self.governor = governor or AuraGovernor()
        self.llm = get_llm()

    async def supervisor_node(self, state: MultiAgentState) -> Dict[str, Any]:
        """Supervisor decides delegation path."""
        intent = state.get("user_intent", "")
        last_msg = state["messages"][-1].content if state["messages"] else ""

        # Deterministic routing logic if next step is clearly established
        if state.get("sql_result") is not None or state.get("rag_context"):
            if not state.get("analysis_result"):
                return {"next_agent": "analyst_agent", "current_agent": "supervisor"}
            return {"next_agent": "FINISH", "current_agent": "supervisor"}

        system = (
            "You are the AURA Multi-Agent Supervisor. Determine which specialist agent should act next:\n"
            "- 'sql_agent': If database queries (employees, salaries, departments) are required.\n"
            "- 'rag_agent': If policy, governance, compliance, or guidelines are requested.\n"
            "- 'analyst_agent': If query results are ready to be synthesized.\n"
            "- 'FINISH': If task is complete.\n"
            "Reply with 'NEXT: <agent_name>'."
        )
        prompt = [SystemMessage(content=system), HumanMessage(content=f"User Intent: {intent}\nLatest: {last_msg}")]
        response = await self.llm.ainvoke(prompt)
        text = response.content.lower()

        if "rag" in text:
            next_agent = "rag_agent"
        elif "analyst" in text:
            next_agent = "analyst_agent"
        elif "finish" in text:
            next_agent = "FINISH"
        else:
            next_agent = "sql_agent"

        return {"next_agent": next_agent, "current_agent": "supervisor"}

    async def sql_agent_node(self, state: MultiAgentState) -> Dict[str, Any]:
        """SQL Specialist agent drafts query and executes strictly through AuraGovernor."""
        intent = state.get("user_intent", "")
        org_id = state.get("org_id", "default-org")
        role = state.get("user_role", "analyst")

        system = (
            "You are an expert SQLite Specialist. The database contains:\n"
            "- employees (id, name, department, role, salary, hire_date, email)\n"
            "- departments (id, name, budget, manager)\n"
            "Write the exact SQL statement needed to fulfill the request. Return only the SQL query."
        )
        prompt = [SystemMessage(content=system), HumanMessage(content=f"Task: {intent}")]
        response = await self.llm.ainvoke(prompt)
        raw_sql = response.content.replace("```sql", "").replace("```", "").strip()

        # Intercept and execute via AURA Governor (NEVER direct execution)
        is_mutate = any(raw_sql.upper().startswith(kw) for kw in ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER"))
        tool_name = "sqlite.execute" if is_mutate else "sqlite.query"

        result = await self.governor.execute_governed_action(
            tool_name=tool_name,
            arguments={"query": raw_sql},
            user_intent=intent,
            org_id=org_id,
            role=role,
        )

        trace = list(state.get("action_trace", []))
        trace.append({
            "agent": "sql_agent",
            "tool": tool_name,
            "query": raw_sql,
            "success": result.success,
            "error": result.error,
        })

        if result.success:
            msg = f"[SQL Agent Executed]: `{raw_sql}`\nResult: {json.dumps(result.output)[:300]}..."
            return {
                "sql_query": raw_sql,
                "sql_result": result.output,
                "action_trace": trace,
                "messages": [AIMessage(content=msg)],
                "current_agent": "sql_agent",
                "next_agent": "analyst_agent",
            }
        else:
            msg = f"[SQL Agent Intercepted/Blocked]: {result.error}"
            return {
                "sql_query": raw_sql,
                "sql_result": None,
                "action_trace": trace,
                "messages": [AIMessage(content=msg)],
                "current_agent": "sql_agent",
                "next_agent": "analyst_agent",
            }

    async def rag_agent_node(self, state: MultiAgentState) -> Dict[str, Any]:
        """Knowledge RAG Agent retrieves policies from Pinecone vector search."""
        intent = state.get("user_intent", "")
        org_id = state.get("org_id", "default-org")

        matches = self.governor.rag_service.search_policies(
            query=intent,
            org_id=org_id,
            top_k=2,
        )
        excerpts = [f"[{m['title']}]: {m['text']}" for m in matches] if matches else ["No specific policy match found."]

        trace = list(state.get("action_trace", []))
        trace.append({
            "agent": "rag_agent",
            "matches_found": len(matches),
            "org_id": org_id,
        })

        msg = f"[Knowledge Agent Retrieved {len(matches)} policies]:\n" + "\n".join(excerpts)
        return {
            "rag_context": excerpts,
            "action_trace": trace,
            "messages": [AIMessage(content=msg)],
            "current_agent": "rag_agent",
            "next_agent": "analyst_agent",
        }

    async def analyst_agent_node(self, state: MultiAgentState) -> Dict[str, Any]:
        """Data Analyst Agent synthesizes database and knowledge findings into executive report."""
        intent = state.get("user_intent", "")
        sql_res = state.get("sql_result")
        rag_ctx = state.get("rag_context", [])
        trace = state.get("action_trace", [])

        # Check if an action was blocked
        blocked = [t for t in trace if not t.get("success", True) and "error" in t]
        if blocked:
            summary = f"### AURA Governance Report\n**Action Blocked:** {blocked[-1].get('error')}\n\nOperation was halted according to organization policy invariants."
            return {
                "analysis_result": summary,
                "final_output": summary,
                "messages": [AIMessage(content=summary)],
                "current_agent": "analyst_agent",
                "next_agent": "FINISH",
            }

        system = "You are the AURA Executive Analyst. Synthesize the findings clearly in professional markdown."
        content = f"Intent: {intent}\nData: {json.dumps(sql_res) if sql_res else 'None'}\nPolicies: {json.dumps(rag_ctx)}"
        response = await self.llm.ainvoke([SystemMessage(content=system), HumanMessage(content=content)])

        return {
            "analysis_result": response.content,
            "final_output": response.content,
            "messages": [response],
            "current_agent": "analyst_agent",
            "next_agent": "FINISH",
        }
