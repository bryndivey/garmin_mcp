# Running / deploying

## Garmin authentication

The server never logs in with a password. Garmin requires MFA, and there is no
way to answer an MFA prompt inside a Cloud Run container — that is what broke
the previous deployment. Tokens are minted locally instead:

```
python garmin_login.py --print-token
```

This writes `~/.garminconnect/garmin_tokens.json` for local runs and prints the
token blob to paste into the deployment secret. The refresh token is long-lived
but not permanent; when the deployment starts failing to authenticate, re-run
this and update the secret.

Store the token blob as a secret:

```
gcloud secrets create garmin-tokens --data-file=$HOME/.garminconnect/garmin_tokens.json
# or, to rotate an existing secret:
gcloud secrets versions add garmin-tokens --data-file=$HOME/.garminconnect/garmin_tokens.json
```

## Local run

```
python garmin_mcp_server.py     # serves streamable-http on PORT (default 8080)
```

## Deploy

```
gcloud run deploy garmin-mcp-server \
    --source . \
    --region us-central1 \
    --allow-unauthenticated \
    --set-secrets GARMIN_EMAIL=garmin-email:latest,GARMIN_PASSWORD=garmin-password:latest,GARMIN_TOKENS_JSON=garmin-tokens:latest
```
