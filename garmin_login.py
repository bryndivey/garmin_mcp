"""
Interactive Garmin Connect login helper.

The MCP server itself never logs in with a password: Garmin requires MFA, and
there is no way to answer an MFA prompt inside a Cloud Run container. Run this
script locally instead. It mints OAuth tokens, saves them to the local token
store, and prints the token blob to feed into GARMINTOKENS for a deployment.

    python garmin_login.py                 # login and store tokens locally
    python garmin_login.py --print-token   # also print the token blob to stdout
"""

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent / ".env")

from garminconnect import Garmin

TOKENSTORE = os.getenv("GARMINTOKENS") or "~/.garminconnect"


def get_mfa() -> str:
    """Prompt for the MFA code Garmin sends by email/SMS."""
    print("\nGarmin Connect MFA required — check your email/phone for the code.")
    return input("Enter MFA code: ").strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--print-token",
        action="store_true",
        help="print the token blob for GARMINTOKENS (contains a refresh token)",
    )
    args = parser.parse_args()

    email = os.environ.get("GARMIN_EMAIL")
    password = os.environ.get("GARMIN_PASSWORD")
    if not email or not password:
        print("GARMIN_EMAIL and GARMIN_PASSWORD must be set in .env", file=sys.stderr)
        return 1

    tokenstore_path = str(Path(TOKENSTORE).expanduser())
    print(f"Logging in as {email} ...")

    garmin = Garmin(email=email, password=password, prompt_mfa=get_mfa)
    garmin.login(tokenstore_path)
    garmin.client.dump(tokenstore_path)

    name = garmin.get_full_name()
    print(f"\nLogged in as {name}.")
    print(f"Tokens written to {tokenstore_path}/garmin_tokens.json")

    if args.print_token:
        print("\n--- GARMINTOKENS value (treat as a password) ---")
        print(garmin.client.dumps())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
