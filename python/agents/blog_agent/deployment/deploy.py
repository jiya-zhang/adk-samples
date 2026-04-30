import os
import sys
import google.auth
import vertexai
from vertexai import agent_engines
from vertexai.preview.reasoning_engines import AdkApp

# Add parent directory to path to allow importing the agent package
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)

import cloudpickle
import blog_agent
from blog_agent.agent import root_agent

cloudpickle.register_pickle_by_value(blog_agent)

def deploy_agent(project_id: str, staging_bucket: str = None, location: str = "us-central1"):
    print(f"🚀 Deploying blog_agent to Vertex AI in {location}...")

    if not staging_bucket:
        staging_bucket = os.getenv("GOOGLE_CLOUD_STORAGE_BUCKET")
        if not staging_bucket:
            raise ValueError("Staging bucket must be specified via --bucket flag or GOOGLE_CLOUD_STORAGE_BUCKET environment variable.")
    print(f"🪣 Using staging bucket: {staging_bucket}")

    vertexai.init(
        project=project_id, location=location, staging_bucket=staging_bucket
    )

    requirements = [
        "google-adk>=1.28.0",
        "google-genai>=0.1.0",
        "google-auth>=2.49.1",
        "python-dotenv>=1.2.2",
    ]

    adk_app = AdkApp(
        agent=root_agent,
        enable_tracing=False,
    )

    env_vars = {
        "DRIVE_SERVICE_ACCOUNT_SECRET_ID": os.getenv("DRIVE_SERVICE_ACCOUNT_SECRET_ID")
    }

    remote_agent = agent_engines.create(
        adk_app,
        requirements=requirements,
        extra_packages=[os.path.join(project_root, "blog_agent")],
        display_name="blog-agent",
        env_vars=env_vars,
    )

    print("✅ Deployment Successful!")
    print(f"Agent Engine ID: {remote_agent.resource_name}")
    return remote_agent.resource_name

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Deploy blog_agent to Vertex AI.")
    parser.add_argument("--bucket", help="The staging GCS bucket name (gs://...)")
    args = parser.parse_args()

    try:
        _, project = google.auth.default()
        active_project = project or os.getenv("GOOGLE_CLOUD_PROJECT")
        if not active_project:
            raise ValueError("Active GCP project could not be determined.")
        deploy_agent(project_id=active_project, staging_bucket=args.bucket)
    except Exception as e:
        print(f"❌ Deployment Failed: {e}")
