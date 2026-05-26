# Render Deployment Guide

## Goal

Create a public URL such as `https://srf-job-hunt.onrender.com` that can be used for SRF members and for the Saramin API application review.

## 1. Push to GitHub

Create a GitHub repository and upload this project folder.

Suggested repository name:

```text
srf-job-hunt
```

## 2. Create Render Blueprint

1. Go to Render.
2. Select `New` > `Blueprint`.
3. Connect the GitHub repository.
4. Render should detect `render.yaml`.
5. Fill required environment variables:
   - `SRF_PASSWORD`: the shared SRF login password.
   - `SARAMIN_ACCESS_KEY`: optional. Add it later if Saramin has not approved the API yet.

## 3. Public URL

After deployment, Render gives the app a URL like:

```text
https://srf-job-hunt.onrender.com
```

Use that URL in the Saramin API application form.

## 4. Persistence Note

The app stores jobs, user comments, settings, and API keys in JSON files. On Render Free, filesystem changes can disappear after a restart or redeploy.

For real club use, add a persistent disk to the Render web service:

```text
Mount path: /opt/render/project/src/runtime-data
```

The app already reads `SRF_DATA_DIR=/opt/render/project/src/runtime-data`, so no code change is needed.

## 5. Saramin Review Text

You can describe the service like this:

```text
SRF Job Hunt is a private, password-protected curation board for SRF members.
It collects finance-related intern and entry-level job postings, shows concise summaries,
and links users back to the original Saramin/KOFIA posting pages for application.
The service does not resell API data and does not expose the Saramin access-key to users.
```
