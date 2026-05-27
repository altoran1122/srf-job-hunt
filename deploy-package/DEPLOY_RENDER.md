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
   - `TELEGRAM_BOT_TOKEN`: optional, required for Telegram alerts.
   - `SARAMIN_ACCESS_KEY`: optional, add after Saramin approves the API.
6. Sensitive values are configured in Render environment variables, not in the SRF Jobs web settings screen.

## 3. Public URL

After deployment, Render gives the app a URL like:

```text
https://srf-job-hunt.onrender.com
```

Use that URL in the Saramin API application form.

## 4. Persistent Disk

The app stores jobs, user comments, notification settings, and local config in JSON files.
Without a Render disk, filesystem changes can disappear after a restart or redeploy.

Add a persistent disk to the Render web service:

```text
Disk name: srf-data
Mount path: /opt/render/project/src/runtime-data
Size: 1 GB
```

The app already reads `SRF_DATA_DIR=/opt/render/project/src/runtime-data`, so no code change is needed.

After adding the disk:

1. Redeploy or restart the service.
2. Save a test comment in SRF Jobs.
3. Redeploy once more.
4. Confirm that the comment still exists.

The first time an empty disk is mounted, Render may hide the old temporary runtime files at that mount path.
If important user data already exists before adding the disk, export or copy it first.

## 5. Saramin Review Text

You can describe the service like this:

```text
SRF Job Hunt is a private, password-protected curation board for SRF members.
It collects finance-related intern and entry-level job postings, shows concise summaries,
and links users back to the original Saramin/KOFIA posting pages for application.
The service does not resell API data and does not expose the Saramin access-key to users.
```
