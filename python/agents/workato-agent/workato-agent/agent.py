import os
import dotenv
from google.adk.agents import LlmAgent
from google.cloud.secretmanager import SecretManagerServiceClient
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset

dotenv.load_dotenv()
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")

system_instruction = """
You are an AI assistant that has access to a list of tools provided by Workato MCP servers.
When a user requests something, always use the tools from the appropriate MCP server to perform that task.

Each Workato MCP server provides tools for one system. You have access to the following tools:
calendar_toolset: manages Google Calendar
email_toolset: manages Gmail
monday_toolset: manages Monday.com
"""

# MCP URL should already include Workato Developer MCP token
# in the format of "?wkt_token=xxx"
def get_mcp_toolset(mcp_url_with_token=None):
    if not mcp_url_with_token:
        print("Warning: MCP URL not found.")
        return

    tools = MCPToolset(
        connection_params=StreamableHTTPConnectionParams(
            url=mcp_url_with_token,
            timeout=60,
        )
    )
    return tools


def get_mcp_url(project_id, secret_id):
    """When running remotely, retrieve the Workato MCP token from Google Cloud Secret Manager."""
    if not project_id:
        raise ValueError("GOOGLE_CLOUD_PROJECT environment variable not set.")

    secret_name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
    client = SecretManagerServiceClient()
    response = client.access_secret_version(request={"name": secret_name})

    return response.payload.data.decode("UTF-8")



PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION")

# Each MCP Server has tools to access one system
# Local runtime uses _MCP_URL to authenticate
# Remote runtime uses _SECRET_ID to access the URL from Secret Manager and then authenticate
CALENDAR_MCP_URL = os.getenv("CALENDAR_MCP_URL")
CALENDAR_SECRET_ID = os.getenv("CALENDAR_SECRET_ID")
EMAIL_MCP_URL = os.getenv("EMAIL_MCP_URL")
EMAIL_SECRET_ID = os.getenv("EMAIL_SECRET_ID")
MONDAY_MCP_URL = os.getenv("MONDAY_MCP_URL")
MONDAY_SECRET_ID = os.getenv("MONDAY_SECRET_ID")


calendar_toolset = get_mcp_toolset(CALENDAR_MCP_URL)
email_toolset = get_mcp_toolset(EMAIL_MCP_URL)
monday_toolset = get_mcp_toolset(MONDAY_MCP_URL)


root_agent = LlmAgent(
    model="gemini-3-flash-preview",
    name="workato_agent",
    instruction=system_instruction,
    tools=[calendar_toolset,email_toolset,monday_toolset],
)