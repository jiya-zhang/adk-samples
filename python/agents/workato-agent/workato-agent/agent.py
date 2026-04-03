import os
import dotenv
from google.adk.agents import LlmAgent
from google.adk.models import Gemini
from google.cloud import secretmanager
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset

dotenv.load_dotenv()

system_instruction = """
You are an AI assistant that has access to a list of tools provided by a Workato MCP server.
When a user requests something, always use the tools from the provided MCP server to perform that task.
"""


def get_workato_mcp_toolset(mcp_token=None, mcp_url=None):
    if not mcp_token:
        print("Warning: MCP token not found.")
        return
    if not mcp_url:
        print("Warning: MCP URL not found.")
        return

    tools = MCPToolset(
        connection_params=StreamableHTTPConnectionParams(
            url=mcp_url,
            headers={
                "Authorization": f"Bearer {mcp_token}"
            },
            timeout=60,
        )
    )
    print("DEBUG tools retrieved")
    return tools


def get_workato_mcp_token(project_id, secret_id):
    """Retrieves the Workato MCP token from Google Cloud Secret Manager."""
    if not project_id:
        raise ValueError("GOOGLE_CLOUD_PROJECT environment variable not set.")

    secret_name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
    client = secretmanager.SecretManagerServiceClient()
    response = client.access_secret_version(request={"name": secret_name})
    print(f"DEBUG token:{response.payload.data.decode('UTF-8')}")
    return response.payload.data.decode("UTF-8")



PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
SECRET_ID = os.getenv("WORKATO_SECRET_ID")
WORKATO_MCP_URL = os.getenv("WORKATO_MCP_URL")
WORKATO_MCP_TOKEN = get_workato_mcp_token(PROJECT_ID,SECRET_ID)

print(f"DEBUG WORKATO_MCP_TOKEN: {WORKATO_MCP_TOKEN}")
print(f"DEBUG WORKATO_MCP_URL: {WORKATO_MCP_URL}")
print(f"DEBUG PROJECT_ID: {PROJECT_ID}")
print(f"DEBUG SECRET_ID: {SECRET_ID}")

workato_toolset = get_workato_mcp_toolset(WORKATO_MCP_TOKEN, WORKATO_MCP_URL)

root_agent = LlmAgent(
    model=Gemini(model="gemini-3-flash-preview"),
    name="workato_agent",
    instruction=system_instruction,
    tools=[workato_toolset],
)