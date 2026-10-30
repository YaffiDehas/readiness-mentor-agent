"""LangGraph workflow (architecture first; a guide, never a gatekeeper - it always ends with a prompt).

guardrails -> context_retrieval (the agent reads the project) -> build_checklist (task-specific architecture topics)
  -> ask_topic (loop: free-text question -> "where to look" if unsure -> labeled as found / reported / none exists / suspected / unknown)
  -> gate: a BLOCKING FACT (endpoint URL, auth...) that nobody could supply?  yes -> stop_report (NO prompt: precise questions for the mentor + session file) -> END
                                                                              no  -> propose_options (architecture unknowns are decided by the agent from the project;
                                                                                     real design choices are the developer's) -> choose_option (loop) -> compose_prompt
  -> eval_prompt -> [compose_prompt again, max 2] -> deliver -> END
"""
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from agent import nodes as n
from agent.state import State

NODES = ("guardrails", "context_retrieval", "build_checklist", "ask_topic", "gate", "stop_report", "propose_options", "choose_option",
         "compose_prompt", "eval_prompt", "deliver")


def build_graph(checkpointer=None):
    g = StateGraph(State)
    for name in NODES:
        g.add_node(name, getattr(n, name))
    g.add_edge(START, "guardrails")
    g.add_conditional_edges("guardrails", n.route_after_guard, {"context_retrieval": "context_retrieval", "end": END})
    g.add_edge("context_retrieval", "build_checklist")
    g.add_conditional_edges("build_checklist", lambda s: "ask_topic" if s["topics"] else "gate", {"ask_topic": "ask_topic", "gate": "gate"})
    g.add_conditional_edges("ask_topic", n.route_after_topic, {"ask_topic": "ask_topic", "gate": "gate", "end": END})
    g.add_conditional_edges("gate", n.route_after_gate, {"stop_report": "stop_report", "propose_options": "propose_options"})
    g.add_edge("stop_report", END)
    g.add_conditional_edges("propose_options", n.route_after_options, {"choose_option": "choose_option", "compose_prompt": "compose_prompt"})
    g.add_conditional_edges("choose_option", n.route_after_choice, {"choose_option": "choose_option", "compose_prompt": "compose_prompt", "end": END})
    g.add_edge("compose_prompt", "eval_prompt")
    g.add_conditional_edges("eval_prompt", n.route_after_eval_prompt, {"compose_prompt": "compose_prompt", "deliver": "deliver"})
    g.add_edge("deliver", END)
    return g.compile(checkpointer or MemorySaver())
