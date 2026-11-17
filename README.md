# Spendings

Personal finance app: import bank statements, extract and categorize transactions, and see where the money goes, track loans, a rented flat, savings and income, plan goals, and ask questions about your own numbers. Local-first (SQLite + files on disk) and deployable to Google Cloud (Cloud Run, Cloud SQL, Cloud Storage, Firebase Auth): see [docs/DEPLOY_GCP.md](docs/DEPLOY_GCP.md).

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

Beyond the spending core, each part has its own page:

| Page | What it does |
|---|---|
| Ask | Ask questions about your own numbers. Claude reads your data through read-only tools and can test what-ifs on the plan without saving them |
| Goals & plan | Month-by-month projection of what is left, where savings go, flat-share rent scenarios, sale of a property and what a new purchase could reach |
| Analysis | Typical month, category explorer, recurring payments, overdraft usage, computed recommendations |
| Savings & net worth | Balances and history per account, positions, allocation, net worth, emergency-fund check |
| Income | Payslips (PDF) parsed into gross, tax withheld and net; tax bracket and PER estimate |
| Loans & credits | Balances and schedules (official amortisation table or computed), debt-service timeline, payoff planner, prepayment and renegotiation what-ifs |
| Rental property | Real cash flow, lease economics after agency fees, checks, sale scenario |

## Layout

```
backend/app
  config.py        settings (env vars / .env)
  auth.py          Firebase ID-token check + e-mail allow-list (off by default)
  models.py        tables: accounts, transactions, categories, loans, properties, snapshots, plan...
  storage.py       document storage: local disk or Cloud Storage
  loans.py         loan maths (projection, payoff, what-if)
  assistant.py     Claude tool loop for the Ask page (read-only)
  extraction/      csv_parser, xlsx_parser, pdf_parser, claude_extractor + dispatcher
  routers/         one module per page
backend/scripts    migrate_to_cloud.py (SQLite -> PostgreSQL + Cloud Storage)
backend/tests      pytest suite (auth, loan maths)
frontend/src       api.ts (typed client), auth.tsx (sign-in gate), pages/
deploy/            Google Cloud setup and deploy scripts
docs/              DEPLOY_GCP.md
```

## Deploying

`./deploy-local.sh` runs everything on your machine. For Google Cloud with sign-in, follow [docs/DEPLOY_GCP.md](docs/DEPLOY_GCP.md).

## Tests

```bash
cd backend && uv run pytest
```
