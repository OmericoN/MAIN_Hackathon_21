import { useEffect, useRef, useState } from 'react'
import { Camera, Check, CircleCheck, FileImage, Pencil, RefreshCcw, Upload, X } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { Button, ErrorState, PageHeader } from '../components/UI'
import { demoIngredients, emojiBySlug } from '../lib/demoData'
import type { Receipt, ReceiptItem } from '../lib/types'

export function ScanScreen() {
  const { api, isDemo } = useAuth()
  const navigate = useNavigate()
  const inputRef = useRef<HTMLInputElement>(null)
  const [receipt, setReceipt] = useState<Receipt | null>(null)
  const [previewUrl, setPreviewUrl] = useState('')
  const [scanning, setScanning] = useState(false)
  const [error, setError] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [draftName, setDraftName] = useState('')
  const [draftQuantity, setDraftQuantity] = useState('')

  useEffect(() => () => { if (previewUrl) URL.revokeObjectURL(previewUrl) }, [previewUrl])

  async function scan(file?: File) {
    if (!file) return
    if (file.size > 10 * 1024 * 1024) { setError('Choose a JPG, PNG, or PDF smaller than 10 MB.'); return }
    const allowed = ['image/jpeg', 'image/png', 'application/pdf']
    if (!allowed.includes(file.type)) { setError('Choose a JPG, PNG, or PDF receipt.'); return }
    setPreviewUrl(file.type === 'application/pdf' ? '' : URL.createObjectURL(file))
    setScanning(true); setError(''); setConfirmed(false); setReceipt(null); setEditingId(null)
    try { setReceipt(await api.scanReceipt(file)) }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'The receipt could not be scanned.') }
    finally { setScanning(false); if (inputRef.current) inputRef.current.value = '' }
  }

  function toggleItem(id: number) {
    setReceipt((current) => current ? { ...current, items: current.items.map((item) => item.id === id ? { ...item, review_status: item.review_status === 'ignored' ? 'accepted' : 'ignored' } : item) } : current)
  }

  function startEdit(item: ReceiptItem) {
    setEditingId(item.id); setDraftName(item.raw_text); setDraftQuantity(item.quantity?.toString() ?? '')
  }

  function saveEdit(id: number) {
    const quantity = Number(draftQuantity)
    if (!draftName.trim() || !Number.isFinite(quantity) || quantity <= 0) { setError('Enter a name and a quantity greater than zero.'); return }
    setReceipt((current) => current ? { ...current, items: current.items.map((item) => item.id === id ? { ...item, raw_text: draftName.trim(), quantity, review_status: 'corrected' } : item) } : current)
    setEditingId(null); setError('')
  }

  async function confirm() {
    if (!receipt) return
    setScanning(true); setError('')
    try { setReceipt(await api.confirmReceipt(receipt)); setConfirmed(true) }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not add the items.') }
    finally { setScanning(false) }
  }

  if (error && !receipt && !scanning) return <div className="screen"><PageHeader title="Scan a receipt" subtitle="Turn a receipt photo into pantry items you can review." /><ErrorState message={error} onRetry={() => { setError(''); inputRef.current?.click() }} /></div>
  const included = receipt?.items.filter((item) => item.review_status !== 'ignored').length ?? 0

  return <div className="screen scan-screen">
    <PageHeader title="Scan a receipt" subtitle="Turn a receipt photo into pantry items you can review." />
    <input ref={inputRef} hidden type="file" aria-label="Receipt image" accept="image/jpeg,image/png,application/pdf" onChange={(event) => void scan(event.target.files?.[0])} />
    <div className={`upload-zone ${scanning ? 'is-scanning' : ''} ${previewUrl ? 'has-preview' : ''}`} onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); void scan(event.dataTransfer.files[0]) }}>
      {previewUrl ? <img className="receipt-preview" src={previewUrl} alt="Uploaded receipt preview" /> : <div className="upload-zone__visual"><FileImage aria-hidden="true" /></div>}
      {scanning ? <div className="upload-zone__content"><span className="scan-beam" /><RefreshCcw className="spin" /><h2>Reading your receipt…</h2><p>Matching each line to your pantry.</p></div> : <div className="upload-zone__content"><h2>{receipt ? 'Receipt ready for review' : 'Take a photo or choose a receipt'}</h2><p>JPG, PNG or PDF · maximum 10 MB</p><div className="upload-actions"><Button onClick={() => inputRef.current?.click()}><Camera /> Take photo</Button><Button variant="secondary" onClick={() => inputRef.current?.click()}><Upload /> {receipt ? 'Replace' : 'Choose file'}</Button></div></div>}
    </div>
    {receipt ? <>
      <section className="receipt-summary" aria-label="Receipt summary">
        <div><CircleCheck /><strong>Receipt processed</strong>{isDemo ? <span className="demo-badge">MVP demo extraction</span> : null}</div>
        <dl><div><dt>Merchant</dt><dd>{receipt.merchant_name ?? 'Unknown'}</dd></div><div><dt>Date</dt><dd>{receipt.purchased_at ? new Date(receipt.purchased_at).toLocaleDateString('en-NL') : '—'}</dd></div><div><dt>Total</dt><dd>{receipt.total_amount === null ? '—' : `€${receipt.total_amount.toFixed(2)}`}</dd></div></dl>
      </section>
      <div className="detected-heading"><div><span>REVIEW</span><h2>Detected items</h2></div><strong>{included} of {receipt.items.length} included</strong></div>
      {!receipt.items.length ? <div className="coming-soon-inline"><FileImage /><div><strong>No lines were returned</strong><small>Try a brighter, flatter photo or use the bundled demo receipt for the MVP flow.</small></div></div> : null}
      <div className="detected-list">{receipt.items.map((item) => {
        const ingredient = demoIngredients.find((entry) => entry.id === item.ingredient_id)
        const isIncluded = item.review_status !== 'ignored'
        const isEditing = editingId === item.id
        return <div className={`${isIncluded ? '' : 'is-ignored'} ${isEditing ? 'is-editing' : ''}`} key={item.id}>
          <button type="button" className={`checkbox ${isIncluded ? 'is-checked' : ''}`} aria-label={`${isIncluded ? 'Exclude' : 'Include'} ${item.raw_text}`} aria-pressed={isIncluded} onClick={() => toggleItem(item.id)}>{isIncluded ? <Check /> : null}</button>
          <span className="detected-emoji" aria-hidden="true">{emojiBySlug[ingredient?.slug ?? ''] ?? '🛍️'}</span>
          {isEditing ? <div className="detected-edit"><label>Item<input value={draftName} onChange={(event) => setDraftName(event.target.value)} /></label><label>Quantity<input type="number" min="0.01" step="0.01" value={draftQuantity} onChange={(event) => setDraftQuantity(event.target.value)} /></label><div><button type="button" className="small-button" onClick={() => saveEdit(item.id)}><Check /> Save</button><button type="button" className="edit-line" aria-label="Cancel edit" onClick={() => setEditingId(null)}><X /></button></div></div> : <>
            <span className="detected-copy"><strong>{item.raw_text}</strong><small>{item.quantity ?? '—'} {item.unit ?? ''}{item.line_total === null ? '' : ` · €${item.line_total.toFixed(2)}`}</small></span>
            <span className="confidence">{item.match_confidence ? `${Math.round(item.match_confidence * 100)}%` : 'Review'}</span>
            <button type="button" className="edit-line" aria-label={`Edit ${item.raw_text}`} onClick={() => startEdit(item)}><Pencil /></button>
          </>}
        </div>
      })}</div>
      {error ? <p className="form-error" role="alert">{error}</p> : null}
      {confirmed ? <div className="confirmation-card"><div><CircleCheck /><span><strong>{included} groceries added</strong><small>Your pantry now includes the reviewed receipt items.</small></span></div><Button onClick={() => navigate('/pantry')}>View pantry</Button></div> : <Button className="wide-save" onClick={() => void confirm()} disabled={scanning || included === 0}>Add {included} items to pantry</Button>}
    </> : !scanning ? <div className="scan-tip"><FileImage /><span><strong>For the cleanest scan</strong><small>Place the receipt flat in bright, even light and keep all four edges visible.</small></span></div> : null}
  </div>
}
