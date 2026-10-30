"""
Modular MCP Server for Garmin Connect Data
"""

import asyncio
import os
import datetime
import requests
from pathlib import Path
from dotenv import load_dotenv

from mcp.server.fastmcp import FastMCP

# Load environment variables from .env file
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

from garminconnect import Garmin, GarminConnectAuthenticationError

# Import all modules
from modules import activity_management
from modules import health_wellness
from modules import user_profile
from modules import devices
from modules import gear_management
from modules import weight_management
from modules import challenges
from modules import training
from modules import workouts
from modules import strength_training
from modules import data_management
from modules import womens_health

# Get credentials from environment
email = os.environ.get("GARMIN_EMAIL")
password = os.environ.get("GARMIN_PASSWORD")
tokenstore = os.getenv("GARMINTOKENS") or "~/.garminconnect"
# Token JSON supplied inline (Cloud Run secret) rather than as a mounted file.
tokenstore_json = os.getenv("GARMIN_TOKENS_JSON")

LOGIN_HELP = (
    "No usable Garmin session. Run 'python garmin_login.py' locally to log in "
    "(it can answer the MFA prompt) and mint tokens, then redeploy with the "
    "GARMIN_TOKENS_JSON secret set to the token blob it prints."
)


def init_api(email, password):
    """Initialize the Garmin API from stored OAuth tokens.

    The server never logs in with a password: Garmin requires MFA and there is
    no way to answer that prompt in a container. Tokens are minted out of band
    by garmin_login.py.
    """
    tokenstore_path = str(Path(tokenstore).expanduser())

    # A token blob from the environment wins; persist it so the client's normal
    # path-based load and refresh-on-expiry both work.
    if tokenstore_json:
        try:
            token_dir = Path(tokenstore_path)
            token_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            token_file = token_dir / "garmin_tokens.json"
            token_file.write_text(tokenstore_json)
            token_file.chmod(0o600)
            print("Using Garmin tokens from GARMIN_TOKENS_JSON.")
        except OSError as err:
            print(f"Could not write tokens from GARMIN_TOKENS_JSON: {err}")

    print(f"Logging in to Garmin Connect with tokens from '{tokenstore_path}'...")
    try:
        garmin = Garmin(email=email, password=password)
        garmin.login(tokenstore_path)
        # Refreshed tokens are worth keeping for the next start.
        try:
            garmin.client.dump(tokenstore_path)
        except OSError as err:
            print(f"Warning: could not persist refreshed tokens: {err}")
        return garmin
    except Exception as err:
        print(f"Garmin login failed: {err}")
        print(LOGIN_HELP)
        return None


class JSONSafeGarminClient:
    """Wrapper around Garmin client that auto-serializes dict/list responses to JSON"""
    
    def __init__(self, garmin_client):
        self._client = garmin_client
    
    def __getattr__(self, name):
        """Proxy all method calls to the underlying client"""
        attr = getattr(self._client, name)
        if callable(attr):
            def wrapper(*args, **kwargs):
                result = attr(*args, **kwargs)
                # If result is dict or list, serialize to JSON
                if isinstance(result, (dict, list)):
                    import json
                    return json.dumps(result, indent=2)
                return result
            return wrapper
        return attr


def main():
    """Initialize the MCP server and register all tools"""
    
    # Initialize Garmin client
    raw_garmin_client = init_api(email, password)
    if not raw_garmin_client:
        print("Failed to initialize Garmin Connect client. Exiting.")
        return
    
    # Wrap it to auto-serialize JSON responses
    garmin_client = JSONSafeGarminClient(raw_garmin_client)
    
    print("Garmin Connect client initialized successfully.")
    
    # Configure all modules with the Garmin client
    activity_management.configure(garmin_client)
    health_wellness.configure(garmin_client)
    user_profile.configure(garmin_client)
    devices.configure(garmin_client)
    gear_management.configure(garmin_client)
    weight_management.configure(garmin_client)
    challenges.configure(garmin_client)
    training.configure(garmin_client)
    workouts.configure(garmin_client)
    strength_training.configure(garmin_client)
    data_management.configure(garmin_client)
    womens_health.configure(garmin_client)
    
    # Create the MCP app
    port = int(os.environ.get("PORT", 8080))
    app = FastMCP("Garmin Connect v1.0", host="0.0.0.0", port=port)
    
    # Register tools from all modules
    app = activity_management.register_tools(app)
    app = health_wellness.register_tools(app)
    app = user_profile.register_tools(app)
    app = devices.register_tools(app)
    app = gear_management.register_tools(app)
    app = weight_management.register_tools(app)
    app = challenges.register_tools(app)
    app = training.register_tools(app)
    app = workouts.register_tools(app)
    app = strength_training.register_tools(app)
    app = data_management.register_tools(app)
    app = womens_health.register_tools(app)
    
    # Add activity listing tool directly to the app
    @app.tool()
    async def list_activities(limit: int = 5) -> str:
        """List recent Garmin activities"""
        try:
            # Use raw client for processing, then format as string
            activities = garmin_client._client.get_activities(0, limit)

            if not activities:
                return "No activities found."

            result = f"Last {len(activities)} activities:\n\n"
            for idx, activity in enumerate(activities, 1):
                result += f"--- Activity {idx} ---\n"
                result += f"Activity: {activity.get('activityName', 'Unknown')}\n"
                result += (
                    f"Type: {activity.get('activityType', {}).get('typeKey', 'Unknown')}\n"
                )
                result += f"Date: {activity.get('startTimeLocal', 'Unknown')}\n"
                result += f"ID: {activity.get('activityId', 'Unknown')}\n\n"

            return result
        except Exception as e:
            return f"Error retrieving activities: {str(e)}"
    
    # Run the MCP server
    app.run(transport="streamable-http")


if __name__ == "__main__":
    main()
