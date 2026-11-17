import HelpBox from '../components/HelpBox'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type ImportSummary } from '../api'
import { useLoad } from '../hooks'

export default function DocumentsPage() {
  const accounts = useLoad(() => api.accounts.list())
  const documents = useLoad(() => api.documents.list())
  const health = useLoad(() => api.health())
  const [accountId, setAccountId] = useState<number | ''>('')
  const [files, setFiles] = useState<FileList | null>(null)
  const [uploading, setUploading] = useState(false)
  const [results, setResults] = useState<{ filename: string; summary: ImportSummary }[]>([])
  const [error, setError] = useState<string | null>(null)

  const accountById = new Map((accounts.data ?? []).map((account) => [account.id, account]))

  async function upload() {
    if (!accountId || !files || files.length === 0) return
    setUploading(true)
    setError(null)
    const collected: typeof results = []
    try {
      for (const file of Array.from(files)) {
        const summary = await api.documents.upload(Number(accountId), file)
        collected.push({ filename: file.name, summary })
      }
      setResults(collected)
      setFiles(null)
      documents.reload()
    } catch (uploadError) {
      setError((uploadError as Error).message)
    } finally {
      setUploading(false)
    }
  }

  async function reextract(documentId: number) {
    const result = await api.documents.reextract(documentId)
    setError(null)
    setResults([{ filename: `Re-extracted document #${documentId}`, summary: { document_id: documentId, status: 'imported', extraction_method: null, transactions_imported: result.added, duplicates_skipped: 0, auto_categorized: 0, warnings: [`${result.updated_labels} label(s) refreshed, ${result.added} added, ${result.removed} removed.`], error: null } }])
    documents.reload()
  }

  async function remove(documentId: number) {
    await api.documents.remove(documentId, true)
    documents.reload()
  }

  return (
    <div>
      <h1>Bank statements</h1>
      <HelpBox title="How do I get my statements?" open={(documents.data?.length ?? 0) === 0}>
        <ol>
          <li>Sign in to your bank's website or app and open <em>Documents</em> / <em>Relevés</em>, or the account history.</li>
          <li>Download the <strong>PDF statements</strong> (one per month), or use <em>Export / Télécharger</em> to get a <strong>CSV or Excel</strong> file covering several months.</li>
          <li>Pick the matching account below and upload. Several files at once are fine, and uploading the same file twice never creates duplicates.</li>
        </ol>
        <strong>Accepted:</strong> PDF (Crédit Mutuel and LCL layouts are read directly; other layouts need the Claude key), CSV, Excel (.xlsx).
        A CSV needs a header with a date, a label and either an amount or debit and credit columns, for example:
        <pre>{`Date;Libellé;Débit;Crédit
02/03/2026;PRLV SEPA EDF CLIENTS;48,20;
05/03/2026;VIREMENT SALAIRE ACME;;2450,00`}</pre>
        <a href="/example-statement.csv" download>Download this example file</a> to test the import.
        Afterwards, check the <a href="/transactions">Transactions</a> to confirm categories.
      </HelpBox>
      <div className="card">
        <h2>Import a bank statement</h2>
        <p className="muted small">
          CSV exports are parsed locally. PDF statements are parsed locally when the layout is recognised
          {health.data?.claude_available ? ', otherwise Claude reads them.' : '; set ANTHROPIC_API_KEY on the backend to let Claude read unknown layouts and invoices.'}
          {' '}Re-uploading the same statement never creates duplicates.
        </p>
        {accounts.data && accounts.data.length === 0 && (
          <div className="alert">Create an <Link to="/accounts">account</Link> first, then come back to upload its statements.</div>
        )}
        <div className="inline-form">
          <select value={accountId} onChange={(event) => setAccountId(event.target.value ? Number(event.target.value) : '')}>
            <option value="">Choose the account…</option>
            {accounts.data?.map((account) => <option key={account.id} value={account.id}>{account.name}{account.bank ? ` (${account.bank})` : ''}</option>)}
          </select>
          <input type="file" multiple accept=".csv,.txt,.pdf,image/*" onChange={(event) => setFiles(event.target.files)} />
          <button className="primary" onClick={upload} disabled={!accountId || !files || uploading}>{uploading ? 'Importing…' : 'Import'}</button>
        </div>
        {error && <div className="alert error" style={{ marginTop: 12 }}>{error}</div>}
        {results.map(({ filename, summary }) => (
          <div key={summary.document_id} className={`alert ${summary.error ? 'error' : 'success'}`} style={{ marginTop: 12 }}>
            <strong>{filename}</strong>: {summary.error ? summary.error : `${summary.transactions_imported} imported, ${summary.duplicates_skipped} duplicates skipped, ${summary.auto_categorized} auto-categorized (${summary.extraction_method}).`}
            {summary.warnings.map((warning) => <div key={warning} className="small muted">{warning}</div>)}
            {!summary.error && summary.transactions_imported > 0 && (
              <div className="small"><Link to="/transactions?uncategorized=1">Review uncategorized transactions →</Link></div>
            )}
          </div>
        ))}
      </div>

      <div className="card">
        <h2>Imported documents</h2>
        <table>
          <thead>
            <tr><th>File</th><th>Account</th><th>Uploaded</th><th>Status</th><th>Imported</th><th>Duplicates</th><th></th></tr>
          </thead>
          <tbody>
            {documents.data?.map((document) => (
              <tr key={document.id}>
                <td>{document.filename}<div className="small muted">{(document.size_bytes / 1024).toFixed(0)} KB · {document.extraction_method ?? '—'}</div></td>
                <td>{document.account_id ? accountById.get(document.account_id)?.name : '—'}</td>
                <td className="muted">{new Date(document.uploaded_at).toLocaleString('fr-FR')}</td>
                <td><span className="badge">{document.status}</span>{document.error && <div className="small negative">{document.error}</div>}</td>
                <td>{document.transactions_imported}</td>
                <td>{document.duplicates_skipped}</td>
                <td className="inline-form" style={{ whiteSpace: 'nowrap' }}>
                  <button onClick={() => reextract(document.id)} title="Re-run extraction and refresh labels, keeping your categories">Re-extract</button>
                  <button className="danger" onClick={() => remove(document.id)} title="Deletes the document and its transactions">Delete</button>
                </td>
              </tr>
            ))}
            {documents.data?.length === 0 && <tr><td colSpan={7} className="muted">Nothing imported yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  )
}
