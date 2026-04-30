import os
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.genai import types, Client
from dotenv import load_dotenv

load_dotenv()

import re
import io
import json
from google.cloud import secretmanager
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
import google.auth

def extract_file_id(url: str) -> str:
    """Extracts file ID from Google Drive URL or returns the ID as is."""
    match = re.search(r'/d/([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)
    match = re.search(r'[?&]id=([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)
    return url

async def generate_blog(tool_context: ToolContext, url: str | None = None) -> str:
    """Generates a blog post based on guidelines in a Google Drive document.

    Call this tool with the url argument if the user provided a Google Drive URL or file ID.
    """
    try:
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        secret_id = os.getenv("DRIVE_SERVICE_ACCOUNT_SECRET_ID")

        if not project_id:
            return "Error: GOOGLE_CLOUD_PROJECT environment variable not set."

        client = secretmanager.SecretManagerServiceClient()
        secret_name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
        response = client.access_secret_version(request={"name": secret_name})
        secret_payload = response.payload.data.decode("UTF-8")
        service_account_info = json.loads(secret_payload)

        creds = service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=["https://www.googleapis.com/auth/drive.readonly"]
        )

        service = build("drive", "v3", credentials=creds)

        file_id = extract_file_id(url)

        file_metadata = service.files().get(fileId=file_id, fields="mimeType", supportsAllDrives=True).execute()
        mime_type = file_metadata.get("mimeType")

        if mime_type == 'application/vnd.google-apps.document':
            request = service.files().export_media(fileId=file_id, mimeType='text/plain')
        else:
            request = service.files().get_media(fileId=file_id, supportsAllDrives=True)

        file_content = io.BytesIO()
        downloader = MediaIoBaseDownload(file_content, request)

        done = False
        while done is False:
            status, done = downloader.next_chunk()

        document_text = file_content.getvalue().decode('utf-8')

        genai_client = Client(vertexai=True, project=project_id, location="global")
        prompt = f"Generate a blog post that adheres to the following guidelines:\n\n{document_text}"

        model_response = genai_client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=[prompt]
        )

        blog_post = model_response.text
        tool_context.state["generated_blog"] = blog_post

        return f"Success: Blog generated successfully.\n\n{blog_post}"

    except Exception as e:
        return f"Error generating blog: {str(e)}"


root_agent = Agent(
    name="blog_agent",
    model=Gemini(model_name="gemini-2.5-flash"),
    instruction="You are a blog generation assistant. You will be given a specs document in the form of a Drive URL."
    "Use the generate_blog tool to generate the blog and return the blog post.",
    description="Generate a blog post from a specs document.",
    tools=[generate_blog],
)

app = App(name="blog_agent", root_agent=root_agent)
