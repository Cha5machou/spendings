# Deploying Spendings on Google Cloud

One container (React frontend + FastAPI backend) on **Cloud Run**, data in **Cloud SQL (PostgreSQL)**,
statements in a private **Cloud Storage** bucket, secrets in **Secret Manager**, sign-in with
**Firebase Authentication (Google)**. Nothing in this repository creates cloud resources by itself: you run the
two scripts below, signed in with your own Google account.

```
browser ──HTTPS──▶ Cloud Run (React + FastAPI) ──▶ Cloud SQL (PostgreSQL)
        Firebase sign-in      │  ├──▶ Cloud Storage (documents)
        (ID token)            │  └──▶ Secret Manager (DB password, Anthropic key)
                              └──▶ Claude API (only for the Ask page and unknown PDF layouts)
```

## What protects your data

- Every `/api` route except `/api/health` and `/api/config` requires a valid Firebase ID token **and** a
  verified Google e-mail address, which must be listed in `ALLOWED_EMAILS` (invite-only) unless `OPEN_SIGNUP=true`.
  Anyone else gets 401 or 403.
- If `AUTH_ENABLED=true` but `FIREBASE_PROJECT_ID` is missing, or neither `ALLOWED_EMAILS` nor `OPEN_SIGNUP` is set,
  the API refuses every request (it fails closed instead of opening up).
- **Each user only sees their own data.** The verified e-mail is the owner of every row (accounts, transactions,
  categories, loans, goals, plan, documents...). The database session filters every query on it, so a router cannot
  read or change another user's rows, even by guessing ids. A new user starts with the default categories.
- Data that existed before accounts (your local SQLite file) is given to `LEGACY_DATA_OWNER` at startup.
- The interactive API docs are switched off when auth is on.
- The database has no authorised networks: only the Cloud Run service account reaches it, through the Cloud SQL
  connector. The bucket blocks public access. Data is encrypted at rest by Google by default.

## Before you start

1. A Google Cloud project with **billing enabled**.
2. `gcloud` signed in as **you**: `gcloud auth login`. Check with `gcloud config list`. The scripts show the account
   and project and ask for confirmation before creating anything. Consider a dedicated configuration:
   `gcloud config configurations create spendings && gcloud auth login`.
3. Docker is not needed: the image is built by Cloud Build.

Rough running cost for one user: the smallest Cloud SQL instance is the only meaningful fixed cost (on the order of
ten euros a month); Cloud Run scales to zero and storage, secrets and builds are close to free at this size. Check the
Google Cloud pricing calculator for current figures. Setting `--deletion-protection` on the database prevents
accidental deletion.

## Steps

```bash
cp deploy/gcp.env.example deploy/gcp.env     # fill PROJECT_ID, REGION, ALLOWED_EMAILS
./deploy/gcp-setup.sh                        # one-time: APIs, bucket, database, secrets, service account
```

**Firebase (console, once).** Open <https://console.firebase.google.com>, *Add project* and pick your existing Google
Cloud project. Then *Build → Authentication → Get started → Sign-in method → Google → Enable*. In *Project settings →
Your apps* create a **Web app** and copy `apiKey` into `deploy/gcp.env` as `FIREBASE_API_KEY`
(`FIREBASE_AUTH_DOMAIN` is `PROJECT_ID.firebaseapp.com`). These values are public identifiers, not secrets.

**Move your data (once).** Run this on the computer that holds your local database, so nothing is typed into a
third-party tool. It copies the database and uploads your statements:

```bash
# terminal 1: a local tunnel to Cloud SQL (install: gcloud components install cloud-sql-proxy, or download the binary)
cloud-sql-proxy PROJECT_ID:REGION:spendings-db --port 5433

# terminal 2:
cd backend
PASSWORD="$(gcloud secrets versions access latest --secret=spendings-db-password)"
uv run python scripts/migrate_to_cloud.py \
  --target "postgresql+psycopg2://spendings:${PASSWORD}@127.0.0.1:5433/spendings" \
  --bucket PROJECT_ID-spendings-documents
```

The script refuses to write into a database that already contains data unless you add `--force`.

**Deploy.**

```bash
./deploy/gcp-deploy.sh
```

It builds the image, deploys to Cloud Run and prints the URL. Finally add that URL's domain under *Firebase →
Authentication → Settings → Authorised domains*, then open the URL and sign in.

## Updating

Run `./deploy/gcp-deploy.sh` again. The database schema is extended automatically at start-up
(new tables and columns are added; nothing is dropped).

## Backups and getting out

- Cloud SQL takes a daily backup (03:00). Export on demand: `gcloud sql export sql spendings-db gs://BUCKET/backup.sql --database=spendings`.
- To go back to local use, point `DATABASE_URL` at a copy of the data or re-import your statements.

## Things to know

- Cloud Run, Cloud SQL and the bucket all live in `REGION` (default `europe-west9`, Paris).
- The Ask page and PDF fallback send the relevant figures or document to the Claude API. Leave `anthropic-api-key` out
  of Secret Manager (skip it in the setup script) to disable both.
- The image build and the Cloud Run deployment have not been run from this repository's author machine; the database
  layer was verified against a local PostgreSQL with the same data (identical results on every page).
