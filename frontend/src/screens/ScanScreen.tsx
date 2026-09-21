import { useRef, useState } from 'react'
import { Camera, Check, CircleCheck, FileImage, Pencil, RefreshCcw, Upload } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { Button, ErrorState, PageHeader } from '../components/UI'
import { demoIngredients, emojiBySlug } from '../lib/demoData'
import type { Receipt } from '../lib/types'

export function ScanScreen() {
  const { api } = useAuth(); const inputRef = useRef<HTMLInputElement>(null)
  const [receipt, setReceipt] = useState<Receipt | null>(null); const [scanning, setScanning] = useState(false); const [error, setError] = useState(''); const [confirmed, setConfirmed] = useState(false)
  async function scan(file?: File) {
    if (!file) return; if (file.size > 10 * 1024 * 1024) { setError('Choose a JPG, PNG, or PDF smaller than 10 MB.'); return }
    setScanning(true); setError(''); setConfirmed(false)
    try { setReceipt(await api.scanReceipt(file)) } catch (reason) { setError(reason instanceof Error ? reason.message : 'The receipt could not be scanned.') } finally { setScanning(false) }
  }
  function toggleItem(id: number) { setReceipt((current) => current ? { ...current, items: current.items.map((item) => item.id === id ? { ...item, review_status: item.review_status === 'ignored' ? 'accepted' : 'ignored' } : item) } : current) }
  async function confirm() { if (!receipt) return; setScanning(true); try { setReceipt(await api.confirmReceipt(receipt)); setConfirmed(true) } catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not add the items.') } finally { setScanning(false) } }
  if (error && !receipt) return <div className="screen"><PageHeader title="Scan a receipt" subtitle="We’ll find your groceries and add them to your pantry." /><ErrorState message={error} onRetry={() => { setError(''); inputRef.current?.click() }} /></div>
  const included = receipt?.items.filter((item) => item.review_status !== 'ignored').length ?? 0
  return <div className="screen scan-screen">
    <PageHeader title="Scan a receipt" subtitle="We’ll find your groceries and add them to your pantry." />
    <input ref={inputRef} hidden type="file" accept="image/jpeg,image/png,application/pdf" onChange={(event) => void scan(event.target.files?.[0])} />
    <div className={`upload-zone ${scanning ? 'is-scanning' : ''}`} onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); void scan(event.dataTransfer.files[0]) }}>
      {scanning ? <><span className="scan-beam" /><RefreshCcw className="spin" /><h2>Reading your receipt…</h2><p>Matching groceries to your pantry.</p></> : <><span className="receipt-emoji">🧾</span><h2>Take a photo or upload a receipt</h2><p>JPG, PNG or PDF · maximum 10 MB</p><div><Button onClick={() => inputRef.current?.click()}><Camera /> Take photo</Button><Button variant="secondary" onClick={() => inputRef.current?.click()}><Upload /> Choose file</Button></div></>}
    </div>
    {receipt ? <>
      <div className="receipt-summary"><div><CircleCheck /><strong>Receipt processed</strong></div><button onClick={() => inputRef.current?.click()}>Replace</button><dl><div><dt>Merchant</dt><dd>{receipt.merchant_name ?? 'Unknown'}</dd></div><div><dt>Date</dt><dd>{receipt.purchased_at ? new Date(receipt.purchased_at).toLocaleDateString('en-NL') : '—'}</dd></div><div><dt>Total</dt><dd>{receipt.total_amount === null ? '—' : `€${receipt.total_amount.toFixed(2)}`}</dd></div></dl></div>
      <div className="detected-heading"><h2>Detected items ({receipt.items.length})</h2><span>{included} included</span></div>
      {!receipt.items.length ? <div className="coming-soon-inline"><span>🧠</span><div><strong>Extraction is awaiting its server workflow</strong><small>The upload record was saved with the current receipt endpoint. Detected lines will fill this reserved review area once extraction runs.</small></div></div> : null}
      <div className="detected-list">{receipt.items.map((item) => { const ingredient = demoIngredients.find((entry) => entry.id === item.ingredient_id); const isIncluded = item.review_status !== 'ignored'; return <div className={isIncluded ? '' : 'is-ignored'} key={item.id}><button className={`checkbox ${isIncluded ? 'is-checked' : ''}`} onClick={() => toggleItem(item.id)}>{isIncluded ? <Check /> : null}</button><span className="detected-emoji">{emojiBySlug[ingredient?.slug ?? ''] ?? '🛍️'}</span><span><strong>{item.raw_text}</strong><small>{item.quantity ?? '—'} {item.unit ?? ''}</small></span><span className="confidence">{item.match_confidence ? `${Math.round(item.match_confidence * 100)}%` : 'Review'}</span><button className="edit-line" aria-label={`Edit ${item.raw_text}`}><Pencil /></button></div> })}</div>
      {error ? <p className="form-error" role="alert">{error}</p> : null}
      {confirmed ? <div className="notice notice--positive"><Check /> Groceries added to your pantry.</div> : <Button className="wide-save" onClick={() => void confirm()} disabled={scanning || included === 0}>Add {included} items to pantry →</Button>}
    </> : <div className="scan-tip"><FileImage /><span><strong>Tip for a better scan</strong><small>Place the receipt flat in bright, even light.</small></span></div>}
  </div>
}
