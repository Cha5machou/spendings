# Spendings

Personal finance app: import bank statements, extract and categorize transactions, and see where the money goes. Local-first (SQLite + files on disk), designed to move to GCP later (Cloud Run, Cloud Storage, Firebase Auth, Firestore).

## Run locally

One command builds the frontend and starts everything on http://localhost:8000 (needs Python 3.12 + [uv](https://docs.astral.sh/uv/) and Node 20+):

```bash
./deploy-local.sh          # build + start (logs in backend/data/server.log)
./deploy-local.sh stop
```

Docker (same image as Cloud Run, built from the repository root):

```bash
docker build -f backend/Dockerfile -t spendings .
docker run -p 8080:8080 -v "$PWD/backend/data:/data" --env-file backend/.env spendings
```

### Development mode (hot reload)

Backend (Python 3.12, [uv](https://docs.astral.sh/uv/)):

```bash
cd backend
cp .env.example .env            # optional: add ANTHROPIC_API_KEY to enable Claude
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

Frontend (Node 20+):

```bash
cd frontend
npm install
npm run dev                     # http://localhost:5173 (proxies /api to the backend)
```

API docs: http://localhost:8000/docs

## How it works

1. **Accounts** – create one per bank account / card / savings product.
2. **Documents** – upload CSV exports or PDF statements for an account.
   - CSV: parsed locally (delimiter and columns are auto-detected: date, libellé, débit/crédit or montant).
   - PDF: parsed locally with `pdfplumber`; if the layout is not recognised and `ANTHROPIC_API_KEY` is set, Claude extracts the lines (structured output).
   - Re-uploading a statement never creates duplicates (hash of account + date + amount + label).
3. **Categorization** – rules (`label contains "carrefour"` → Groceries) run on import. Setting a category by hand offers to create a rule, which is then applied to the other matching transactions. With Claude enabled, "Categorize uncategorized with Claude" fills in the rest (marked `ai`, still editable).
4. **Dashboard** – income / expenses / savings per month, expenses by category, top merchants.

Categories have a *kind*: `expense`, `income`, `savings` (counted as saved, not spent) or `transfer` (between your own accounts, ignored in totals).

## Layout

```
backend/app
  config.py        settings (env vars / .env)
  models.py        Account, Category, CategoryRule, Document, Transaction
  storage.py       document storage (local; GCS to be added)
  extraction/      csv_parser, pdf_parser, claude_extractor + dispatcher
  categorizer.py   rule engine
  seed.py          default categories and rules
  routers/         accounts, categories, documents, transactions, dashboard
frontend/src
  api.ts           typed API client
  pages/           Dashboard, Transactions, Documents, Accounts, Categories
```

## Roadmap

- Loans & mortgage tracking (remaining capital, end dates, monthly cost)
- Rental property (rent received vs. charges, fees, yield)
- Savings & net worth (Livret A, LDDS, PEA, assurance-vie, CTO, crypto)
- Goals (short / medium / long term) and recommendations (incl. PER, PEE/PERCO…)
- Mortgage simulations for a new purchase
- GCP deployment: Cloud Run (backend `Dockerfile` included), GCS storage backend, Firebase Auth, Firestore
