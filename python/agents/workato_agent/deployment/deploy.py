import logging
import os
import sys

import vertexai
from dotenv import load_dotenv
from vertexai import agent_engines
from vertexai.preview.reasoning_engines import AdkApp

# Add the project root to sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

load_dotenv()

from workato_agent.agent import root_agent

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION")
STAGING_BUCKET = os.getenv("GOOGLE_CLOUD_STORAGE_BUCKET")

if not PROJECT_ID or not LOCATION or not STAGING_BUCKET:
    raise ValueError("GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION, and GOOGLE_CLOUD_STORAGE_BUCKET must be set in environment or .env")

vertexai.init(
    project=PROJECT_ID,
    location=LOCATION,
    staging_bucket=f"gs://{STAGING_BUCKET}",
)

# Pass these variables to the deployed agent
env_vars = {
    "GOOGLE_CLOUD_PROJECT": PROJECT_ID,
    "GOOGLE_CLOUD_LOCATION": LOCATION,
    "CALENDAR_SECRET_ID": os.getenv("CALENDAR_SECRET_ID", ""),
    "EMAIL_SECRET_ID": os.getenv("EMAIL_SECRET_ID", ""),
    "MONDAY_SECRET_ID": os.getenv("MONDAY_SECRET_ID", ""),
}

app = AdkApp(
    agent=root_agent,
    enable_tracing=True,
    env_vars=env_vars,
)

logger.info("Deploying Workato Agent to Vertex AI Agent Engine...")

remote_app = agent_engines.create(
    app,
    display_name="workato-audit-pipeline",
    requirements=[
        "google-cloud-aiplatform[adk,agent-engines]>=1.100.0,<2.0.0",
        "google-adk>=1.5.0,<2.0.0",
        "python-dotenv",
        "google-cloud-secret-manager",
        "google-cloud-firestore",
    ],
    extra_packages=[
        "./workato-agent",
    ],
)

logger.info(
    f"Deployed agent successfully, resource name: {remote_app.resource_name}"
)
