import os
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.genai import types, Client
from dotenv import load_dotenv

load_dotenv()

async def generate_image(prompt: str, tool_context: ToolContext) -> str:
    """Generates an image based on the prompt using Nano Banana and stores it in context.

    Args:
        prompt: The description of the image to generate.
    """
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    # Nano Banana typically requires location="global" on Vertex AI
    client = Client(vertexai=True, project=project_id, location="global")

    model = "gemini-3.1-flash-image-preview"

    config = types.GenerateContentConfig(
        response_modalities=["IMAGE", "TEXT"]
    )

    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=config
        )

        parts = response.candidates[0].content.parts
        image_parts = [p for p in parts if p.text is None and p.inline_data]

        if not image_parts:
            return "Failed to generate image: No image found in model response."

        image_data = image_parts[0].inline_data.data
        import base64
        image_b64 = base64.b64encode(image_data).decode('utf-8')

        # Store in tool context state
        tool_context.state.setdefault("generated_images", []).append(image_b64)

        # Store in the agent's session artifact
        mime_type = image_parts[0].inline_data.mime_type or "image/png"
        image_artifact = types.Part.from_bytes(
            data=image_data, mime_type=mime_type
        )

        import time
        filename = f"generated_image_{int(time.time())}.png"
        version = await tool_context.save_artifact(
            filename=filename, artifact=image_artifact
        )
        
        # Store the latest filename in state for other tools to access
        tool_context.state["latest_image_filename"] = filename

        return f"Success: Image stored in agent's session artifact '{filename}' (version {version})."

    except Exception as e:
        return f"Error generating image: {str(e)}"

async def upload_image(folder_id: str, tool_context: ToolContext) -> str:
    """Uploads the generated image from the session artifact to a Google Drive folder.

    Args:
        folder_id: The ID of the Google Drive folder to upload the image to.
        tool_context: The tool context to use for storing the image.
    """

    try:
        # Get the latest image filename from state
        filename = tool_context.state.get("latest_image_filename", "generated_image.png")
        
        # Read the image from the agent's session artifact
        image_artifact = await tool_context.load_artifact(filename)
        if not image_artifact:
            return f"Error: No generated image found for '{filename}' in session artifacts."

        if isinstance(image_artifact, types.Part):
            image_data = image_artifact.inline_data.data
            mime_type = image_artifact.inline_data.mime_type or "image/png"
        else:
            image_data = image_artifact
            mime_type = "image/png"

        # Upload to Google Drive
        import io
        import google.auth
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaIoBaseUpload

        import os
        import json
        from google.cloud import secretmanager
        from google.oauth2 import service_account

        project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        secret_id = os.getenv("DRIVE_SERVICE_ACCOUNT_SECRET_ID")

        if not project_id:
            return "Error: GOOGLE_CLOUD_PROJECT environment variable not set."

        try:
            client = secretmanager.SecretManagerServiceClient()
            secret_name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
            response = client.access_secret_version(request={"name": secret_name})
            secret_payload = response.payload.data.decode("UTF-8")
            service_account_info = json.loads(secret_payload)

            creds = service_account.Credentials.from_service_account_info(
                service_account_info,
                scopes=["https://www.googleapis.com/auth/drive.file"]
            )
        except Exception as secret_error:
            return f"Error retrieving service account from Secret Manager '{secret_id}': {str(secret_error)}"

        service = build("drive", "v3", credentials=creds)

        import time
        file_metadata = {
            'name': f'generated_image_{int(time.time())}.png',
            'parents': [folder_id]
        }
        media = MediaIoBaseUpload(io.BytesIO(image_data), mimetype=mime_type)
        drive_file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        file_id = drive_file.get('id')

        return f"Success: Image uploaded to Google Drive: '{file_id}'"

    except Exception as e:
        return f"Error uploading image: {str(e)}"

root_agent = Agent(
    name="image_agent",
    model=Gemini(model_name="gemini-2.5-flash"),
    instruction="You are an image generation assistant. You will receive information on "
    "(1) an image generation prompt, and (2) a Google Drive folder ID to upload the generated image to."
    "First, generate an image using given prompt with generate_image tool. Then, upload the image with upload_image tool.",
    description="Generates images using Nano Banana and stores them.",
    tools=[generate_image, upload_image],
)

app = App(name="image_agent", root_agent=root_agent)
