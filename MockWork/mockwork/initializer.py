from __future__ import annotations

import json
import re
from typing import Any

from .io import (
    BACKGROUND_FILE,
    MEMBERS_FILE,
    PROJECT_SCOPE_FILE,
    TASKS_FILE,
    log_llm_interaction,
    read_json,
    read_text,
    save_members_to_markdown,
    save_tasks_to_markdown,
    write_json,
    write_text,
)
from .llm import LLMClient
from .prompts import member_generation_prompt, system_prompt, task_generation_prompt


def extract_json_from_markdown(md_content: str) -> dict[str, Any] | list[Any] | None:
    """Extract JSON from markdown code blocks."""
    json_pattern = r"```json\s*([\s\S]*?)\s*```"
    matches = re.findall(json_pattern, md_content, flags=re.IGNORECASE)
    parsed_blocks: list[Any] = []
    for match in matches:
        try:
            parsed_blocks.append(json.loads(match))
        except json.JSONDecodeError:
            continue
    if not parsed_blocks:
        return None
    if len(parsed_blocks) == 1:
        return parsed_blocks[0]
    return parsed_blocks


def normalize_asset_list(value: Any, wrapper_key: str) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        if wrapper_key in value:
            wrapped = value[wrapper_key]
            if isinstance(wrapped, list):
                return wrapped
            raise ValueError(f"{wrapper_key} must be a list")
        return [value]
    if isinstance(value, list):
        return value
    raise ValueError(f"Expected {wrapper_key} to be a list or object")
    return None


def load_project_assets() -> tuple[str, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    background = read_text(BACKGROUND_FILE)
    project_scope = {}
    try:
        project_scope = read_json(PROJECT_SCOPE_FILE)
    except (FileNotFoundError, json.JSONDecodeError):
        project_scope = {}
    
    # Try to load from MD files first, extract JSON from code blocks
    try:
        members_md = read_text(MEMBERS_FILE)
        members = extract_json_from_markdown(members_md)
        if members is None:
            members = read_json(MEMBERS_FILE)
    except (FileNotFoundError, json.JSONDecodeError):
        members = read_json(MEMBERS_FILE)
    
    try:
        tasks_md = read_text(TASKS_FILE)
        tasks = extract_json_from_markdown(tasks_md)
        if tasks is None:
            tasks = read_json(TASKS_FILE)
    except (FileNotFoundError, json.JSONDecodeError):
        tasks = read_json(TASKS_FILE)
    
    members = normalize_asset_list(members, "members")
    tasks = normalize_asset_list(tasks, "tasks")
    
    return background, members, tasks, project_scope


def initialize_project(
    *,
    llm: LLMClient,
    background: str,
    member_count: int,
    org_structure: str = "",
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    print("正在生成成员档案...")
    member_system = system_prompt("member_generation")
    member_prompt = member_generation_prompt(background, member_count, org_structure)
    members_response = llm.json(member_system, member_prompt)
    members = members_response["members"]
    log_llm_interaction(
        step="initialize:members",
        source="initializer",
        system=member_system,
        prompt=member_prompt,
        response=str(members_response),
    )
    
    print("正在生成任务池...")
    task_system = system_prompt("task_generation")
    task_prompt = task_generation_prompt(background, members)
    tasks_response = llm.json(task_system, task_prompt)
    tasks = tasks_response["tasks"]
    log_llm_interaction(
        step="initialize:tasks",
        source="initializer",
        system=task_system,
        prompt=task_prompt,
        response=str(tasks_response),
    )

    # Save background as markdown
    write_text(BACKGROUND_FILE, background.strip() + "\n")
    
    # Save as JSON for code to read
    write_json(MEMBERS_FILE, members)
    write_json(TASKS_FILE, tasks)
    
    # Also save as markdown for human readability
    save_members_to_markdown(members)
    save_tasks_to_markdown(tasks)
    
    return background, members, tasks
