# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import base64
import datetime
import json
import os
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from zoneinfo import ZoneInfo

from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager
from dotenv import load_dotenv
from google import genai
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors import AgentEngineSandboxCodeExecutor
from google.adk.memory import VertexAiMemoryBankService
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.cloud import firestore, storage
from google.genai import types

from .a2ui_utils import a2ui_callback

load_dotenv()

PROJECT_ID = "qwiklabs-gcp-01-3f7f306be789"
BUCKET_NAME = "travel-concierge-media-qwiklabs-gcp-01-3f7f306be789"
MEMORY_BANK_ID = "3004444110200242176"


def _get_db():
    return firestore.Client(project=PROJECT_ID)


# Initialize Agent Platform sandbox code executor from deployment_metadata.json
code_executor = None
metadata_file = Path(__file__).parent.parent / "deployment_metadata.json"
if metadata_file.exists():
    try:
        with open(metadata_file) as f:
            meta = json.load(f)
        ae_id = meta.get("remote_agent_runtime_id")
        if ae_id:
            code_executor = AgentEngineSandboxCodeExecutor(agent_engine_resource_name=ae_id)
    except Exception as e:
        print(f"Warning: Could not initialize AgentEngineSandboxCodeExecutor: {e}")


# WRITE: Memory Bank callback to extract durable preferences, allergies, and facts at turn completion
async def generate_memories_callback(callback_context: CallbackContext):
    try:
        await callback_context.add_session_to_memory()
    except Exception as e:
        print(f"Memory service not available or failed: {e}")
    return None


def memory_bank_service_builder():
    return VertexAiMemoryBankService(
        project=PROJECT_ID,
        location="us-east1",
        agent_engine_id=MEMORY_BANK_ID,
    )


def generate_destination_image(
    prompt: str,
    filename_prefix: str = "preview",
    tool_context: ToolContext | None = None,
) -> str:
    """Generates a visual image preview for a travel destination or attraction, saves it as an artifact, uploads it to Cloud Storage, and returns the public image URL.

    Args:
        prompt: Detailed description of the image to generate (e.g., 'Golden Pavilion temple in Kyoto in autumn with vibrant maple leaves').
        filename_prefix: Short prefix for the saved file name (e.g., 'kyoto', 'tokyo').
        tool_context: ADK ToolContext injected automatically by the framework.

    Returns:
        The public HTTPS URL of the generated image.
    """
    client = genai.Client(vertexai=True, project=PROJECT_ID, location="global")
    response = client.models.generate_content(
        model="gemini-3.1-flash-lite-image",
        contents=f"Generate a realistic travel photo of: {prompt}",
    )

    for part in response.candidates[0].content.parts:
        if part.inline_data:
            image_bytes = part.inline_data.data
            mime_type = part.inline_data.mime_type or "image/png"
            ext = "png" if "png" in mime_type else "jpg"
            clean_prefix = filename_prefix.lower().replace(" ", "_")
            filename = f"{clean_prefix}_{uuid.uuid4().hex[:8]}.{ext}"

            # 1. Save with tool_context.save_artifact so it appears in Playground's Artifacts panel
            if tool_context:
                artifact_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
                tool_context.save_artifact(filename=filename, artifact=artifact_part)

            # 2. Upload same bytes to public GCS bucket directly (no writing to local file)
            storage_client = storage.Client(project=PROJECT_ID)
            bucket = storage_client.bucket(BUCKET_NAME)
            blob = bucket.blob(filename)
            blob.upload_from_string(image_bytes, content_type=mime_type)

            return f"https://storage.googleapis.com/{BUCKET_NAME}/{filename}"

    return "Failed to generate image."


def generate_destination_video(
    prompt: str,
    filename_prefix: str = "video",
    tool_context: ToolContext | None = None,
) -> str:
    """Generates a short promotional travel video for a destination or attraction using Google's Omni model (gemini-omni-flash-preview) in global region, saves it as an artifact, uploads it to Cloud Storage, and returns the public video URL.

    Args:
        prompt: Description of the video to generate (e.g., 'A scenic aerial view of Kyoto bamboo forest in autumn').
        filename_prefix: Short prefix for the saved file name (e.g., 'kyoto', 'tokyo').
        tool_context: ADK ToolContext injected automatically by the framework.

    Returns:
        The public HTTPS URL of the generated video.
    """
    client = genai.Client(vertexai=True, project=PROJECT_ID, location="global")
    clean_prefix = filename_prefix.lower().replace(" ", "_")
    filename = f"{clean_prefix}_{uuid.uuid4().hex[:8]}.mp4"
    mime_type = "video/mp4"

    video_bytes = None
    try:
        interaction = client.interactions.create(
            model="gemini-omni-flash-preview",
            input=f"Generate a short travel video of: {prompt}",
        )
        if hasattr(interaction, "output_video") and interaction.output_video:
            data = interaction.output_video.data
            if isinstance(data, str):
                video_bytes = base64.b64decode(data)
            elif isinstance(data, bytes):
                video_bytes = data
    except Exception as e:
        print(f"Error calling Interactions API for gemini-omni-flash-preview: {e}")

    if not video_bytes:
        return "Failed to generate video using gemini-omni-flash-preview."

    # 1. Save with tool_context.save_artifact so it shows up in Playground's Artifacts panel
    if tool_context:
        artifact_part = types.Part.from_bytes(data=video_bytes, mime_type=mime_type)
        tool_context.save_artifact(filename=filename, artifact=artifact_part)

    # 2. Upload same bytes directly to public GCS bucket (no writing to local file)
    storage_client = storage.Client(project=PROJECT_ID)
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(filename)
    blob.upload_from_string(video_bytes, content_type=mime_type)

    return f"https://storage.googleapis.com/{BUCKET_NAME}/{filename}"


def geocode_address(address: str) -> str:
    """Converts a street address or location name into geographic latitude and longitude coordinates using Google Maps Geocoding API.

    Args:
        address: The address or place name to geocode (e.g., 'Kyoto Station, Japan', '1600 Amphitheatre Pkwy, Mountain View, CA').

    Returns:
        A JSON string containing the formatted address, latitude, and longitude.
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return "Error: GOOGLE_MAPS_API_KEY environment variable is not set."

    try:
        url = f"https://maps.googleapis.com/maps/api/geocode/json?address={urllib.parse.quote(address)}&key={api_key}"
        req = urllib.request.Request(url, headers={"User-Agent": "TravelConciergeAgent/1.0"})
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())

        results = data.get("results", [])
        if not results:
            return f"No geocoding results found for address: '{address}'"

        first = results[0]
        location = first.get("geometry", {}).get("location", {})
        return json.dumps(
            {
                "formatted_address": first.get("formatted_address"),
                "latitude": location.get("lat"),
                "longitude": location.get("lng"),
            },
            indent=2,
        )
    except Exception as e:
        return f"Error geocoding address '{address}': {str(e)}"


def find_nearby_places(
    latitude: float,
    longitude: float,
    place_type: str = "restaurant",
    radius_meters: float = 1000.0,
) -> str:
    """Finds nearby points of interest (e.g., restaurants, tourist_attraction, lodging, cafe) near a specific lat/lng using Places API (New).

    Args:
        latitude: Latitude coordinate of search center.
        longitude: Longitude coordinate of search center.
        place_type: Type of place to search for (e.g., 'restaurant', 'tourist_attraction', 'lodging', 'cafe', 'museum').
        radius_meters: Radius in meters around coordinates to search (default 1000m).

    Returns:
        A JSON string listing nearby places with name, formatted address, and location coordinates.
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return "Error: GOOGLE_MAPS_API_KEY environment variable is not set."

    try:
        url = "https://places.googleapis.com/v1/places:searchNearby"
        payload = json.dumps(
            {
                "includedTypes": [place_type],
                "maxResultCount": 5,
                "locationRestriction": {
                    "circle": {
                        "center": {"latitude": latitude, "longitude": longitude},
                        "radius": radius_meters,
                    }
                },
            }
        ).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location",
            "User-Agent": "TravelConciergeAgent/1.0",
        }

        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())

        places = data.get("places", [])
        if not places:
            return f"No nearby '{place_type}' places found within {radius_meters}m of ({latitude}, {longitude})."

        results = []
        for p in places:
            display_name = p.get("displayName", {}).get("text", "Unknown Name")
            address = p.get("formattedAddress", "")
            loc = p.get("location", {})
            results.append(
                {
                    "name": display_name,
                    "address": address,
                    "location": {
                        "latitude": loc.get("latitude"),
                        "longitude": loc.get("longitude"),
                    },
                }
            )

        return json.dumps(results, indent=2)
    except Exception as e:
        return f"Error finding nearby places: {str(e)}"


def get_live_weather(city: str) -> str:
    """Fetches real-time live weather forecast and temperature for any city using Open-Meteo public API.

    Args:
        city: Name of the city to get live weather for (e.g. 'Kyoto', 'Tokyo', 'Barcelona', 'Reykjavik').

    Returns:
        A JSON string containing real-time temperature (°C), wind speed, and today's max/min forecast.
    """
    try:
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(city)}&count=1"
        req = urllib.request.Request(geo_url, headers={"User-Agent": "TravelConciergeAgent/1.0"})
        with urllib.request.urlopen(req) as resp:
            geo_data = json.loads(resp.read().decode())

        results = geo_data.get("results", [])
        if not results:
            return f"Could not find coordinates for city: {city}"

        loc = results[0]
        lat, lon = loc["latitude"], loc["longitude"]
        country = loc.get("country", "")

        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true&daily=temperature_2m_max,temperature_2m_min&timezone=auto"
        req_w = urllib.request.Request(weather_url, headers={"User-Agent": "TravelConciergeAgent/1.0"})
        with urllib.request.urlopen(req_w) as resp_w:
            w_data = json.loads(resp_w.read().decode())

        current = w_data.get("current_weather", {})
        daily = w_data.get("daily", {})

        return json.dumps(
            {
                "city": loc.get("name", city),
                "country": country,
                "latitude": lat,
                "longitude": lon,
                "current_temperature_celsius": current.get("temperature"),
                "windspeed_kmh": current.get("windspeed"),
                "max_temp_today_celsius": daily.get("temperature_2m_max", [None])[0],
                "min_temp_today_celsius": daily.get("temperature_2m_min", [None])[0],
            },
            indent=2,
        )
    except Exception as e:
        return f"Error fetching live weather for {city}: {str(e)}"


def search_destinations(query: str = "") -> str:
    """Searches travel destinations in the catalog database.

    Args:
        query: Optional search keyword (e.g., 'Japan', 'beach', 'culture', 'temple'). If empty, returns all destinations.

    Returns:
        A JSON string containing matching destination summaries.
    """
    db = _get_db()
    docs = db.collection("destinations").stream()
    results = []
    q = query.lower().strip()
    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        if not q:
            results.append(data)
        else:
            searchable_text = f"{data.get('title', '')} {data.get('description', '')} {' '.join(data.get('highlights', []))}".lower()
            if q in searchable_text:
                results.append(data)
    if not results:
        return f"No destinations found matching '{query}'."
    return json.dumps(results, indent=2)


def get_destination_details(destination_id: str) -> str:
    """Gets detailed information for a specific destination by its ID.

    Args:
        destination_id: The ID of the destination (e.g., 'tokyo-japan', 'kyoto-japan').

    Returns:
        A JSON string with the destination details, or an error message if not found.
    """
    db = _get_db()
    doc_ref = db.collection("destinations").document(destination_id)
    doc = doc_ref.get()
    if not doc.exists:
        return f"Destination with ID '{destination_id}' not found."
    data = doc.to_dict()
    data["id"] = doc.id
    return json.dumps(data, indent=2)


def save_itinerary(user_id: str, title: str, destination: str, days: int, activities: list[str]) -> str:
    """Saves a trip itinerary to Firestore for a user.

    Args:
        user_id: The ID or username of the traveler (e.g. 'default_user').
        title: Title of the itinerary (e.g., '5-Day Tokyo Adventure').
        destination: Destination name (e.g., 'Tokyo').
        days: Number of days for the trip.
        activities: A list of planned activities or highlights.

    Returns:
        A success message with the saved itinerary ID.
    """
    db = _get_db()
    itinerary_data = {
        "user_id": user_id,
        "title": title,
        "destination": destination,
        "days": days,
        "activities": activities,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    doc_ref = db.collection("itineraries").document()
    doc_ref.set(itinerary_data)
    return f"Itinerary saved successfully with ID: {doc_ref.id}"


def get_user_itineraries(user_id: str = "default_user") -> str:
    """Retrieves all saved itineraries for a given user.

    Args:
        user_id: The user ID to fetch itineraries for. Defaults to 'default_user'.

    Returns:
        A JSON string list of saved itineraries for the user.
    """
    db = _get_db()
    docs = db.collection("itineraries").where("user_id", "==", user_id).stream()
    results = []
    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        results.append(data)
    if not results:
        return f"No saved itineraries found for user '{user_id}'."
    return json.dumps(results, indent=2)


def get_current_time(query: str) -> str:
    """Simulates getting the current time for a city.

    Args:
        query: The name of the city to get the current time for.

    Returns:
        A string with the current time information.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        tz_identifier = "America/Los_Angeles"
    else:
        return f"Sorry, I don't have timezone information for query: {query}."

    tz = ZoneInfo(tz_identifier)
    now = datetime.datetime.now(tz)
    return f"The current time for query {query} is {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}"


# Build A2UI v0.8 system prompt
schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

instruction = schema_manager.generate_system_prompt(
    role_description=(
        "You are the Travel Concierge Agent, a personalized AI travel assistant.\n"
        "IMPORTANT - USER ALLERGIES & DIETARY RESTRICTIONS:\n"
        "You MUST explicitly remember, track, and strictly observe all stated user allergies (e.g. peanuts, tree nuts, gluten, shellfish, dairy, eggs, soy) "
        "and dietary restrictions across all past and current conversations. Always cross-check preloaded user memories for allergies before recommending restaurants, "
        "food tours, or meal plans, and explicitly highlight safety warnings or allergen-free options for the user.\n\n"
        "You help users search destination catalogs, geocode addresses, find nearby places/attractions/restaurants, "
        "fetch real-time live weather forecasts, generate visual preview photos, execute Python code for budget and timeline calculations in a secure sandbox, "
        "save itineraries to Firestore, and recall saved itineraries.\n"
        "Always use your search_destinations and get_destination_details tools to look up real destination data from Firestore, "
        "use geocode_address and find_nearby_places for location and nearby spots, "
        "use get_live_weather when asked about current weather or travel conditions, "
        "and use code execution for complex budget calculations and currency math."
    ),
    workflow_description="Analyze the request and return structured UI when appropriate.",
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        '{"Image": {"url": {"literalString": "https://..."}}}. Never point an '
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)

root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-flash-latest",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    code_executor=code_executor,
    instruction=instruction,
    tools=[
        PreloadMemoryTool(),
        generate_destination_image,
        generate_destination_video,
        geocode_address,
        find_nearby_places,
        get_live_weather,
        search_destinations,
        get_destination_details,
        save_itinerary,
        get_user_itineraries,
        get_current_time,
    ],
    after_agent_callback=generate_memories_callback,
    after_model_callback=a2ui_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)
