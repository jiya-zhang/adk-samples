import os
import datetime
from google.cloud import firestore
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
from google.adk.tools import ToolContext
from google.cloud.secretmanager import SecretManagerServiceClient
import dotenv

dotenv.load_dotenv()

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
LOCATION = os.getenv("MODEL_LOCATION", "global")

def get_user_info(tool_context: ToolContext):
    """Returns the user ID and session ID for the current user."""
    try:
        user_id = tool_context._invocation_context.user_id
        session_id = tool_context._invocation_context.session.id
        content = tool_context._invocation_context.user_content
        query_parts = [part.text for part in content.parts if hasattr(part, 'text')]
        user_query = " ".join(query_parts).strip()
        return user_id, session_id, user_query
    except:
        raise RuntimeError("Failed to retrieve user information.")

def audit_user_query(user_id: str, session_id: str, user_query: str) -> str:
    """Records user information, query, and timestamp to a remote database, and returns access token for downstream agents.

    Args:
        user_id: The unique identifier for the end user (e.g., email or user ID).
        user_query: The request or query text the user asks.

    Returns:
        Audit confirmation and authentication validation endpoint.
    """
    try:
        # Initialise Firestore DB client
        db = firestore.Client(project=PROJECT_ID, database="user-audits")

        audit_record = {
            "user_id": user_id,
            "session_id": session_id,
            "user_query": user_query,
            "timestamp": firestore.SERVER_TIMESTAMP,
        }

        db.collection("audits").add(audit_record)
        return f"Audit successful for user {user_id}. Authentication layer passed and execution can proceed."
    except Exception as e:
        raise RuntimeError(f"Audit proxy layer failed to log user query: {e}. Aborting workflow execution.")

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
    if not project_id or not secret_id:
        raise ValueError("GOOGLE_CLOUD_PROJECT or secret_id environment variable not set.")

    try:
        secret_name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
        client = SecretManagerServiceClient()
        response = client.access_secret_version(request={"name": secret_name})
        return response.payload.data.decode("UTF-8")
    except Exception as e:
        raise RuntimeError(f"Failed to retrieve MCP URL from Secret Manager: {e}")

# Each MCP Server has tools to access one system
# Local runtime uses _MCP_URL to authenticate
# Remote runtime uses _SECRET_ID to access the URL from Secret Manager and then authenticate


"""
EMAIL_SECRET_ID = os.getenv("EMAIL_SECRET_ID")
EMAIL_MCP_URL = os.getenv("EMAIL_MCP_URL", get_mcp_url(PROJECT_ID, EMAIL_SECRET_ID))

MONDAY_SECRET_ID = os.getenv("MONDAY_SECRET_ID")
MONDAY_MCP_URL = os.getenv("MONDAY_MCP_URL", get_mcp_url(PROJECT_ID, MONDAY_SECRET_ID))
"""

CALENDAR_SECRET_ID = os.getenv("CALENDAR_SECRET_ID")
CALENDAR_MCP_URL = os.getenv("CALENDAR_MCP_URL")

def get_calendar_toolset():
    return get_mcp_toolset(CALENDAR_MCP_URL)

def get_current_time() -> str:
    """Returns the current local time and date."""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

#email_toolset = get_mcp_toolset(EMAIL_MCP_URL)
#monday_toolset = get_mcp_toolset(MONDAY_MCP_URL)
