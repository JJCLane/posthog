from ee.hogai.core.plan_mode import (
    APPROVAL_TASK_PROMPT,
    ONBOARDING_TASK_PROMPT,
    PLAN_MODE_PROMPT_TEMPLATE,
    PLANNING_TASK_PROMPT,
)

CHAT_PLAN_AGENT_PROMPT = """
{{{role}}}

{{{plan_mode}}}

{{{tone_and_style}}}

{{{writing_style}}}

{{{basic_functionality}}}

{{{switching_modes}}}

{{{task_management}}}

{{{onboarding_task}}}

{{{planning_task}}}

{{{approval_task}}}

{{{switch_to_execution}}}

{{{tool_usage_policy}}}

{{{billing_context}}}

{{{groups}}}
""".strip()

CHAT_PLAN_MODE_PROMPT = PLAN_MODE_PROMPT_TEMPLATE.format(
    task_type="product management",
    notebook_type="plan",
    next_step_instruction="Get user approval, then switch to `execution` mode using switch_mode to proceed with the actual task",
    task_type_short="task",
)

# Re-export for convenience
CHAT_ONBOARDING_TASK_PROMPT = ONBOARDING_TASK_PROMPT
CHAT_PLANNING_TASK_PROMPT = PLANNING_TASK_PROMPT
CHAT_APPROVAL_TASK_PROMPT = APPROVAL_TASK_PROMPT

SWITCHING_TO_EXECUTION_PROMPT = """
<execution_mode>
Once the user has approved the plan, switch to `execution` mode using switch_mode to proceed with the actual task.
</execution_mode>
"""
