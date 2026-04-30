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
import base64
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

def get_closest_aspect_ratio(width: int, height: int) -> str:
    """Determines the closest supported aspect ratio for Gemini outpainting."""
    supported = {
        "1:1": 1.0,
        "2:3": 2/3,
        "3:2": 3/2,
        "3:4": 3/4,
        "4:3": 4/3,
        "9:16": 9/16,
        "16:9": 16/9,
        "21:9": 21/9
    }
    target = width / height
    closest = min(supported.keys(), key=lambda k: abs(supported[k] - target))
    return closest

async def load_image(tool_context: ToolContext, url: str | None = None) -> str:
    """Loads an image for processing.

    Call this tool without arguments to automatically detect and load an image that the user uploaded directly via the chat interface.
    Call this tool with the url argument if the user provided a Google Drive URL or file ID.
    """
    try:
        try:
            artifact = None
            if url:
                try:
                    artifact = await tool_context.load_artifact(url)
                except Exception:
                    pass
            if not artifact:
                artifacts = await tool_context.list_artifacts()
                if artifacts:
                    artifact = await tool_context.load_artifact(artifacts[0])

            if artifact:
                if isinstance(artifact, types.Part):
                    image_data = artifact.inline_data.data
                    mime_type = artifact.inline_data.mime_type or "image/png"
                else:
                    image_data = artifact
                    mime_type = "image/png"

                image_b64 = base64.b64encode(image_data).decode('utf-8')

                tool_context.state["loaded_image"] = image_b64
                tool_context.state["loaded_image_mime_type"] = mime_type
                tool_context.state["image_in_artifact"] = True

                return f"Success: Image loaded from session artifacts and stored in context. Size: {len(image_data)} bytes."
        except Exception:
            pass

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
        mime_type = file_metadata.get("mimeType", "image/png")

        request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
        file_content = io.BytesIO()
        downloader = MediaIoBaseDownload(file_content, request)

        done = False
        while done is False:
            status, done = downloader.next_chunk()

        image_data = file_content.getvalue()

        image_b64 = base64.b64encode(image_data).decode('utf-8')

        tool_context.state["loaded_image"] = image_b64
        tool_context.state["loaded_image_mime_type"] = mime_type

        return f"Success: Image downloaded from Google Drive and stored in context. Size: {len(image_data)} bytes."

    except Exception as e:
        return f"Error loading image from Google Drive: {str(e)}"

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
        contents = [prompt]

        if "image_in_artifact" in tool_context.state:
            if tool_context.state["image_in_artifact"] == True:
                image = await tool_context.load_artifact()
                if isinstance(image, types.Part):
                    image_data = image.inline_data.data
                    mime_type = image.inline_data.mime_type or "image/png"
                else:
                    image_data = image
                    mime_type = "image/png"

                image_part = types.Part.from_bytes(
                    data=image_data,
                    mime_type=mime_type
                )
                contents.insert(0, image_part)


        # Load image from context if it exists
        elif "loaded_image" in tool_context.state:
            image_b64 = tool_context.state["loaded_image"]
            mime_type = tool_context.state.get("loaded_image_mime_type", "image/png")
            image_data = base64.b64decode(image_b64)

            image_part = types.Part.from_bytes(
                data=image_data,
                mime_type=mime_type
            )
            contents.insert(0, image_part)

        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=config
        )

        parts = response.candidates[0].content.parts
        image_parts = [p for p in parts if p.text is None and p.inline_data]

        if not image_parts:
            return "Failed to generate image: No image found in model response."

        image_data = image_parts[0].inline_data.data
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
        drive_file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id',
            supportsAllDrives=True
        ).execute()
        file_id = drive_file.get('id')

        return f"Success: Image uploaded to Google Drive: '{file_id}'"

    except Exception as e:
        return f"Error uploading image: {str(e)}"

async def resize_image(target_width: int, target_height: int, tool_context: ToolContext) -> str:
    """Resizes the loaded base image to user-specified pixel dimensions without distortion.

    Intelligently expands the image canvas via outpainting using Gemini,
    and then precisely resizes to target dimensions via Pillow.

    Args:
        target_width: The target width of the image in pixels.
        target_height: The target height of the image in pixels.
    """
    if "loaded_image" not in tool_context.state:
        return "Error: No image found in context. Please load an image first using the load_image tool."

    try:
        from PIL import Image

        image_b64 = tool_context.state["loaded_image"]
        mime_type = tool_context.state.get("loaded_image_mime_type", "image/png")
        image_data = base64.b64decode(image_b64)

        closest_aspect_ratio = get_closest_aspect_ratio(target_width, target_height)

        # Use Gemini outpainting
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        client = Client(vertexai=True, project=project_id, location="global")

        config = types.GenerateContentConfig(
            response_modalities=["IMAGE", "TEXT"],
            image_config=types.ImageConfig(
                aspect_ratio=closest_aspect_ratio,
                image_size="1K"
            )
        )

        image_part = types.Part.from_bytes(
            data=image_data,
            mime_type=mime_type
        )

        prompt = (
            f"Expand and outpaint the provided image to match the {closest_aspect_ratio} aspect ratio. "
            "Ensure all visual content is intact without stretching, cropping, or distorting, "
            "and preserve the original artistic style completely."
        )

        response = client.models.generate_content(
            model="gemini-3.1-flash-image-preview",
            contents=[image_part, prompt],
            config=config
        )

        parts = response.candidates[0].content.parts
        image_parts = [p for p in parts if p.text is None and p.inline_data]

        if not image_parts:
            return "Failed to outpaint image: No image returned by Gemini."

        generated_image_data = image_parts[0].inline_data.data

        # Precision resizing with Pillow
        img = Image.open(io.BytesIO(generated_image_data))
        resized_img = img.resize((target_width, target_height), Image.Resampling.LANCZOS)

        output_bytes = io.BytesIO()
        # Save the final image
        resized_img.save(output_bytes, format="PNG")
        final_image_data = output_bytes.getvalue()

        # Save as agent session artifact
        import time
        filename = f"resized_image_{int(time.time())}.png"

        resized_artifact = types.Part.from_bytes(
            data=final_image_data, mime_type="image/png"
        )
        version = await tool_context.save_artifact(
            filename=filename, artifact=resized_artifact
        )

        # Save to state for next steps
        tool_context.state["latest_image_filename"] = filename

        final_image_b64 = base64.b64encode(final_image_data).decode('utf-8')
        tool_context.state.setdefault("generated_images", []).append(final_image_b64)

        return f"Success: Image resized to {target_width}x{target_height} without distortion and stored in session artifact '{filename}' (version {version})."

    except Exception as e:
        return f"Error intelligently resizing image: {str(e)}"

root_agent = Agent(
    name="image_agent",
    model=Gemini(model_name="gemini-2.5-flash"),
    instruction="You are an image generation assistant. "
    "First, use the load_image tool to load any image. "
    "If the user uploaded an image directly via the chat interface, call the load_image tool without the url argument. "
    "If the user provided a Google Drive URL, call the load_image tool with the url argument. "
    "Then, resize the loaded image using the resize_image tool. "
    "Finally, upload the resized image to a Google Drive folder using the upload_image tool.",
    description="Resize a base image and upload new image to Drive.",
    tools=[load_image, upload_image, resize_image],
)

app = App(name="image_agent", root_agent=root_agent)
