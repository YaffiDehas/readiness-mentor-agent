from typing import TypedDict


class State(TypedDict, total=False):
    # input / control
    task: str
    project_root: str             # "" = NO project: nothing is scanned and nothing may be claimed about the code
    no_project: bool
    attachments: list[dict]       # [{"name", "text"}]
    session: dict                 # a saved session (topics already settled, blocked facts) to continue from
    run_id: str
    in_scope: bool
    cancelled: bool
    warnings: list[str]
    # project scan (the agent reads the project itself before it asks anything)
    project_facts: str
    project_files: list[str]
    dependencies: list[str]       # package names found in the manifests
    scan: dict
    evidence_files: list[str]
    retrieval_log: list[str]
    # task-specific architecture checklist
    requirements: list[str]       # extracted from the task text
    topics: list[dict]            # {id,title,question,why,category,blocker,search_terms,mockable,status,answer,paths,deps,notes,candidates,mentor,mentor_question}; status: verified|reported|absent|suspected|unknown|mock_ok|mentor_answered|mentor_needed|open
    topic_idx: int
    blocked: list[dict]           # blocking facts nobody could supply (non-empty -> no prompt is produced)
    # implementation choices
    decisions: list[dict]
    decision_idx: int
    # result
    final_prompt: str
    prompt_round: int
    eval_issues: list[dict]
    final_prompt_eval_text: str
    correction_round: int
    brief_accepted: bool
    outcome: str                  # "prompt" | "needs_mentor"
    session_out: dict             # what the developer needs to continue after the mentor answered
    final_message: str
    saved_path: str
