import os
import dotenv
from google.adk.agents import LlmAgent, SequentialAgent
from google.cloud.secretmanager import SecretManagerServiceClient
from .tools import get_user_info, audit_user_query, get_calendar_toolset, get_current_time
from .prompt import (
    audit_proxy_agent_instruction,
    workato_agent_instruction,
)

dotenv.load_dotenv()
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")
os.environ.setdefault("LOCATION", "global")

audit_proxy_agent = LlmAgent(
    model="gemini-3-flash-preview",
    name="audit_proxy_agent",
    instruction=audit_proxy_agent_instruction,
    tools=[get_user_info, audit_user_query],
    description="Audit proxy agent that extracts user information and logs user query and timestamp to a remote database.",
)

workato_agent = LlmAgent(
    model="gemini-3-flash-preview",
    name="workato_agent",
    instruction=workato_agent_instruction,
    tools=[get_calendar_toolset(), get_current_time],
    description="Uses tools to perform calendar, email, and Monday.com actions.",
)

root_agent = SequentialAgent(
    name="root_agent",
    sub_agents=[audit_proxy_agent, workato_agent],
    description="Executes linear pipeline: audit_proxy_agent -> workato_agent.",
)