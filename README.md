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

The menu follows the order a newcomer should work in. **Get started** shows a checklist and where you are.

**1 · Set up**

| Step | Page | What you do |
|---|---|---|
| 1 | Accounts | Add your current accounts, cards and savings accounts, with the authorised overdraft |
| 2 | Payslips | Upload PDF payslips, or type them in; gives your real income, tax and bracket |
| 3 | Credits & loans | Add each credit (or import the amortisation table of a loan offer); payoff planner and what-ifs |
| 4 | Rental property | Only if you rent one out: lease terms, agency fees, real cash flow, sale scenario |
| 5 | Bank statements | Upload PDF, CSV or Excel statements (an example file is provided) |
| 6 | Transactions | Check categories month by month; each fix can become a rule |
| 7 | Goals | Write your own goals and assumptions; the projection tells you whether they are on track |

**2 · Analyse**: Dashboard (income, expenses, savings), Analysis (where the money goes, recurring payments, what to improve), Savings & net worth, and Ask (questions about your own numbers, answered by Claude from your data, read-only).

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
