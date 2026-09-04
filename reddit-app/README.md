# Project Luvcraft — Reddit Devvit Companion Bridge

This Devvit application serves as the official on-Reddit companion and data bridge for **Project Luvcraft**.

## Capabilities

1. **Automated Event Forwarding:** Ingests live community posts (`PostSubmit`) in target gaming subreddits and securely forwards sanitized data to the Project Luvcraft FastAPI webhook receiver (`POST /api/v1/webhooks/reddit`).
2. **Interactive Subreddit Widget:** Renders a native Reddit post component displaying live community sentiment and vibe check metrics.

## Running / Testing Locally

\\ash
# Install Devvit CLI
npm install -g devvit

# Login with your Reddit account
devvit login

# Start playtest session
npm run dev
\