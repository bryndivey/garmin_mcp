[![MseeP.ai Security Assessment Badge](https://mseep.net/pr/taxuspt-garmin-mcp-badge.png)](https://mseep.ai/app/taxuspt-garmin-mcp)

# Garmin MCP Server

This Model Context Protocol (MCP) server connects to Garmin Connect and exposes your fitness and health data to Claude and other MCP-compatible clients.

## Features

- List recent activities
- Get detailed activity information
- Access health metrics (steps, heart rate, sleep)
- View body composition data
- Write weight training plans back to Garmin (see below)

### Weight training

The server can author strength workouts, not just read data:

- `create_strength_workout` — build a session from sets/reps/weights and
  optionally put it on the calendar
- `create_strength_training_plan` — upload and schedule a multi-session plan
  in one call
- `schedule_workout` / `unschedule_workout` — manage the training calendar
- `delete_workout` — remove a workout from the library
- `list_strength_exercises` — search Garmin's exercise catalogue

Exercises are given by Garmin's own names, e.g.:

```json
[{"exercise": "BARBELL_BACK_SQUAT", "sets": 4, "reps": 5,
  "weight_kg": 82.5, "rest_seconds": 180},
 {"exercise": "PLANK", "sets": 3, "duration_seconds": 45, "rest_seconds": 30}]
```

`modules/exercise_catalogue.py` holds 1828 category/exercise pairs verified
against the live Garmin API. Garmin silently discards an exercise name it does
not recognise — leaving a step with no exercise on it — so the server validates
names up front and reports the mistake instead.

## Setup

1. Install the required packages on a new environment:

```bash
virtualenv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```


2. Create a `.env` file in the project root with your Garmin credentials:

```
GARMIN_EMAIL=your.email@example.com
GARMIN_PASSWORD=your-password
```

3. Log in once to mint OAuth tokens:

```bash
python garmin_login.py
```

The server authenticates with these tokens rather than a password, since Garmin
may require an MFA code that only an interactive login can answer. See
[RUN.md](RUN.md) for deploying with the tokens.

## Running the Server

### With Claude Desktop

1. Create a configuration in Claude Desktop:

Edit your Claude Desktop configuration file:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

Add this server configuration:

```json
{
  "mcpServers": {
    "garmin": {
      "command": "python", // if you created a new environment this should be "<root_folder>/.venv/bin/python"
      "args": ["<path to>/garmin_mcp/garmin_mcp_server.py"]
    }
  }
}
```

Replace the path with the absolute path to your server file.

2. Restart Claude Desktop

### With MCP Inspector

For testing, you can use the MCP Inspector:

```bash
npx @modelcontextprotocol/inspector python /Users/adomingues/Documents/claude_filesystem/garmin_mcp/garmin_mcp_server.py
```

## Usage Examples

Once connected in Claude, you can ask questions like:

- "Show me my recent activities"
- "What was my sleep like last night?"
- "How many steps did I take yesterday?"
- "Show me the details of my latest run"

## Security Note

This server requires your Garmin Connect credentials in the `.env` file. Keep this file secure and never commit it to a repository.

## Troubleshooting

If you encounter login issues:

1. Verify your credentials in the `.env` file are correct
2. Re-run `python garmin_login.py` — tokens expire and need reminting
3. Ensure the garminconnect package is up to date

Note that a wrong password can surface as a bogus MFA prompt: Garmin's rejection
page carries the title "GARMIN Authentication Application", which the client
library reads as an MFA challenge. If you are asked for a code that never
arrives, check the password first.

For other issues, check the Claude Desktop logs at:
- macOS: `~/Library/Logs/Claude/mcp-server-garmin.log`
- Windows: `%APPDATA%\Claude\logs\mcp-server-garmin.log`