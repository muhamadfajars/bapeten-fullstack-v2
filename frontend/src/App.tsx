import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { DragEvent, ReactNode } from 'react';
import {
  Activity, AlertCircle, ArrowRight, CalendarDays, Check, CheckCircle2,
  ChevronDown, ChevronRight, CircleHelp, CloudUpload,
  ExternalLink, Eye, FileCheck2, FileClock, FileText, FolderOpen, HardDriveUpload,
  Home, Info, Layers3, LayoutDashboard, LoaderCircle, Menu,
  RotateCcw, Search, Trash2, UploadCloud, UsersRound, X,
} from 'lucide-react';
import bapetenLogo from './assets/bapeten-logo.png';
import { CATEGORIES, categoryById } from './data/categories';
import { matchingTotals, sortMatchingSections } from './lib/matching';
import {
  newApplication, uploadFile, deleteFile, analyze, jobStatus, latestJob, jobResults, listFiles,
  fetchPreviewFile, fetchEvidencePage, updateFileCategory
} from './api';
import type { AnalysisResult, AnalysisJob } from './api';
import { classifyFile, classifyByFilename } from './lib/classifier';
import { monitorAnalysis, retryRead } from './lib/analysisMonitor';
import { applyClassification, analysisBlocker } from './lib/uploadState';
import Glyph from './components/Glyph';
import type { CategoryId, MatchRow, MatchSection, MatchStatus, UploadItem } from './types/models';
import { PERSONNEL_TYPES } from './types/models';

const ID = () => `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
const MAX_FILE = 40 * 1024 * 1024;
const SUPPORTED_EXTENSIONS = new Set(['pdf', 'jpg', 'jpeg', 'png', 'bmp', 'webp', 'tif', 'tiff', 'docx']);
const sizeLabel = (bytes: number) => bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
const dateLabel = (iso: string) => new Date(iso).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' });
const analysisDateLabel = (timestamp: number) => {
  const date = new Date(timestamp * 1000);
  return `${date.toLocaleDateString('id-ID')}, ${date.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })}`;
};

type PageId = 'ringkasan' | 'upload' | 'formulir' | 'matching' | 'dokumen';
type Filter = 'ALL' | MatchStatus;
type Toast = { tone: 'success' | 'warning' | 'info'; message: string } | null;

const NAV: Array<{ id: PageId; label: string; icon: typeof Home }> = [
  { id: 'ringkasan', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'upload', label: 'Upload Dokumen', icon: HardDriveUpload },
  { id: 'formulir', label: 'Formulir Permohonan', icon: FileText },
  { id: 'matching', label: 'Hasil Matching', icon: Activity },
  { id: 'dokumen', label: 'Dokumen', icon: FolderOpen },
];

function Brand() {
  return (
    <div className="brand-lockup">
      <img src={bapetenLogo} alt="Logo BAPETEN" className="brand-logo" />
      <div className="brand-text">
        <div className="brand-name">BAPETEN</div>
        <div className="brand-description">Badan Pengawas Tenaga Nuklir</div>
      </div>
    </div>
  );
}

function Sidebar({ active, navigate, open, close, working }: { active: PageId; navigate: (id: PageId) => void; open: boolean; close: () => void; working: boolean }) {
  return <>
    {open && <button className="sidebar-mask" onClick={close} aria-label="Tutup menu" />}
    <aside className={`sidebar ${open ? 'mobile-open' : ''}`}>
      <Brand />
      <div className="sidebar-label">WORKSPACE</div>
      <nav aria-label="Navigasi utama" className="nav-list">
        {NAV.map(({ id, label, icon: Icon }) => (
          <button key={id} className={`nav-link ${active === id ? 'active' : ''}`} aria-current={active === id ? 'page' : undefined} onClick={() => { navigate(id); close(); }}>
            <Icon size={19} strokeWidth={1.9} /><span>{label}</span>
            {id === 'matching' && working && <span className="nav-progress" title="Analisis sedang berjalan"><LoaderCircle className="analysis-spinner" size={16} aria-hidden="true"/><span className="sr-only"> — Analisis sedang berjalan</span></span>}
            {active === id && <span className="active-marker" />}
          </button>
        ))}
      </nav>
      <div className="sidebar-foot">
        <div className="sidebar-copyright">© 2026 BAPETEN · Asisten Evaluasi Perizinan RDI</div>
      </div>
    </aside>
  </>;
}

function SectionHeading({ eyebrow, title, description, action }: { eyebrow: string; title: string; description: string; action?: ReactNode }) {
  return <div className="section-header">
    <div><span className="eyebrow">{eyebrow}</span><h2>{title}</h2><p>{description}</p></div>
    {action && <div className="section-action">{action}</div>}
  </div>;
}

function SummaryCard({ icon, label, value, note, tone }: { icon: ReactNode; label: string; value: string | number; note: string; tone: string }) {
  return <div className="summary-card">
    <div className={`summary-icon tone-${tone}`}>{icon}</div>
    <div className="summary-content"><div className="metric-caption">{label}</div><div className="metric-value">{value}</div><div className="metric-note">{note}</div></div>
  </div>;
}

function rowMatchesFilter(row: MatchRow, filter: Filter, query: string): boolean {
  if (filter !== 'ALL' && row.status !== filter) return false;
  const search = query.trim().toLocaleLowerCase('id-ID');
  return !search || `${row.field} ${row.expected} ${row.observed}`.toLocaleLowerCase('id-ID').includes(search);
}

function matchingSectionTitle(section: MatchSection): string {
  // Backend supplies a controlled subtype label, never the uploaded filename.
  if (section.category === 'personel' && /^Dokumen Personel - (SIP|SIB|Surat Perintah|Sertifikat Kompetensi|Surat Izin Kerja|Surat Keterangan Kerja|Surat Penunjukan Tugas|Evaluasi Dosis|Evaluasi Dosis \/ Zero Check)$/.test(section.name)) {
    return section.name;
  }
  return categoryById(section.category)?.name ?? 'Dokumen';
}

function ScoreBadge({ status }: { status: MatchStatus }) {
  return <span className={`status-chip status-${status.toLowerCase()}`}><span className="status-dot" />{status}</span>;
}

function Accordion({ title, subtitle, icon, children, open, onToggle, count }: { title: string; subtitle?: string; icon?: ReactNode; children: ReactNode; open: boolean; onToggle: () => void; count?: ReactNode }) {
  return <div className={`accordion ${open ? 'accordion-open' : ''}`}>
    <button className="accordion-toggle" type="button" onClick={onToggle} aria-expanded={open}>
      <div className="accordion-label">{icon && <span className="accordion-icon">{icon}</span>}<span><strong>{title}</strong>{subtitle && <small>{subtitle}</small>}</span></div>
      <div className="accordion-right">{count}<ChevronDown className="accordion-chevron" size={19} /></div>
    </button>
    {open && <div className="accordion-body">{children}</div>}
  </div>;
}

function DataPair({ label, value }: { label: string; value: string }) {
  return <div className="data-pair"><div>{label}</div><strong>{value}</strong></div>;
}

function InlineSourcePreview({ documentId, page }: { documentId: string; page?: number }) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    if (!page || page < 1) return;
    let active = true;
    let allocated: string | null = null;
    const application = sessionStorage.getItem('bapeten_application_id');
    if (!application) { setError('Permohonan belum tersedia'); return; }
    fetchEvidencePage(application,documentId,page).then(blob=>{
      if (!active) return;
      allocated=URL.createObjectURL(blob);
      setBlobUrl(allocated);
    }).catch(err=>{if(active) setError(err instanceof Error?err.message:'Halaman gagal dimuat')});
    return () => { active=false; if(allocated) URL.revokeObjectURL(allocated); };
  }, [documentId,page]);
  return <div className="inline-source-preview">
    {(!page || page < 1) && <span className="inline-preview-state">Halaman pengesahan belum terdeteksi.</span>}
    {page && !blobUrl && !error && <span className="inline-preview-state">Memuat halaman pengesahan…</span>}
    {error && <span className="inline-preview-error">{error}</span>}
    {blobUrl && <img src={blobUrl} alt={`Bukti pengesahan hanya halaman PDF ${page}`} className="inline-evidence-image"/>}
  </div>;
}

function ApprovalEvidence({row}:{row:MatchRow}) {
  const [opened,setOpened]=useState(false);
  const pages=row.detail?.pages || [];
  const sourcePage=pages[0] || row.page;
  return <details className="evidence-accordion" onToggle={ev=>setOpened(ev.currentTarget.open)}>
    <summary><span>Lihat halaman Lembar Pengesahan (verifikasi visual)</span><ChevronDown size={18}/></summary>
    {opened && <div className="evidence-body">
      <strong>{row.detail?.heading || 'Lembar Pengesahan'}</strong>
      <p>{sourcePage ? `Hanya PDF halaman ${sourcePage} ditampilkan.` : 'Halaman pengesahan belum dapat ditentukan otomatis.'} Tanda tangan/stempel tetap memerlukan verifikasi visual.</p>
      {row.document_id && sourcePage && <InlineSourcePreview documentId={row.document_id} page={sourcePage}/>}
    </div>}
  </details>;
}

function MaintenanceEvidence({row}:{row:MatchRow}) {
  const [opened,setOpened]=useState(false);
  const pages=row.detail?.pages || [];
  const freqs=row.detail?.frequencies || [];
  const params=row.detail?.parameters || [];
  return <details className="evidence-accordion maintenance-accordion" onToggle={ev=>setOpened(ev.currentTarget.open)}>
    <summary><span>Klausul Uji Kesesuaian</span><ChevronDown size={18}/></summary>
    {opened && <div className="evidence-body maintenance-detail" aria-label="Klausul Uji Kesesuaian">
      <p className="maintenance-source">Sumber: PDF {pages.length > 1 ? `halaman ${pages[0]}–${pages[pages.length-1]}` : pages.length ? `halaman ${pages[0]}` : 'belum diketahui'}</p>
      <div className="maintenance-columns">
        <div><h4>Frekuensi</h4>{freqs.length ? <ul>{freqs.map((s,i)=><li key={i}>{s}</li>)}</ul> : <p>Frekuensi belum dapat diekstrak.</p>}</div>
        <div><h4>Parameter yang diuji</h4>{params.length ? <ul>{params.map((s,i)=><li key={i}>{s}</li>)}</ul> : <p>Parameter belum dapat diekstrak.</p>}</div>
      </div>
    </div>}
  </details>;
}

function StreamlitDetails({section, filter, search}: {section: MatchSection; filter: Filter; search: string}) {
  const specials = section.rows.filter((r) => (r.detail?.type === 'approval' || r.detail?.type === 'maintenance') && rowMatchesFilter(r, filter, search));
  return <div className="matching-extras">
    {specials.filter(r => r.detail?.type === 'approval').map(r => <ApprovalEvidence key={r.id} row={r}/>)}
    {specials.filter(r => r.detail?.type === 'maintenance').map(r => <MaintenanceEvidence key={r.id} row={r}/>)}
  </div>;
}

function MatchingSection({ section, search, filter, onRowClick, expandedByDefault = false }: { section: MatchSection; search: string; filter: Filter; onRowClick: (r: MatchRow, s: MatchSection) => void; expandedByDefault?: boolean }) {
  const [open, setOpen] = useState(expandedByDefault);
  const stats = useMemo(() => matchingTotals([section]), [section]);
  const filtered = section.rows.filter((row) => rowMatchesFilter(row, filter, search));
  return <div className="matching-section streamlit-style">
    <button className="match-section-header" type="button" onClick={() => setOpen(!open)} aria-expanded={open}>
      <span className="match-heading-group"><span className={`category-icon category-${section.category}`}><Glyph name={categoryById(section.category)?.icon ?? 'file'} /></span>
        <span><strong>{matchingSectionTitle(section)}</strong><small>{filtered.length === section.rows.length ? `${filtered.length} field` : `${filtered.length} dari ${section.rows.length} field ditampilkan`}</small></span></span>
      <span className="match-pills"><span className="pill green">{stats.match} Match</span>{stats.review > 0 && <span className="pill amber">{stats.review} Review</span>}{stats.mismatch > 0 && <span className="pill red">{stats.mismatch} Mismatch</span>}</span>
      <ChevronDown size={19} className={`match-chevron ${open ? 'rotated' : ''}`} />
    </button>
    {open && <div className="match-section-content">
      <div className="streamlit-stats" aria-label="Ringkasan seluruh field dalam kategori">
        <div><span>Kecocokan terbukti</span><strong>{stats.percentage.toFixed(1)}%</strong></div>
        <div><span>MATCH</span><strong>{stats.match}</strong></div>
        <div><span>REVIEW</span><strong>{stats.review}</strong></div>
        <div><span>MISMATCH</span><strong>{stats.mismatch}</strong></div>
      </div>
      <div className="table-scroll matching-table-scroll" tabIndex={0} role="region" aria-label={`Tabel ${matchingSectionTitle(section)}`}>
        <table className="matching-table"><thead><tr><th scope="col">Field</th><th scope="col">Formulir</th><th scope="col">Dokumen</th><th scope="col">Skor</th><th scope="col">Status</th></tr></thead><tbody>
          {filtered.map((row, i) => <tr key={`${row.id}-${i}`} className={`matching-row-${row.status.toLowerCase()}`} onClick={() => onRowClick(row, section)}>
            <td className="field-column"><button type="button" className="field-detail-button" aria-label={`Lihat detail ${row.field}`} onClick={event => { event.stopPropagation(); onRowClick(row, section); }}>{row.field}</button></td><td>{row.expected}</td><td className={row.observed === '—' ? 'empty-observed' : ''}>{row.observed}
              {row.document_id && <button type="button" className="matching-evidence-button" aria-label={`Lihat Bukti ${row.field}`} onClick={event => { event.stopPropagation(); onRowClick(row, section); }}><Eye size={14} aria-hidden="true"/> Lihat Bukti</button>}
            </td>
            <td className="score-column">{row.score === null ? '—' : `${row.score.toFixed(1)}%`}</td><td><span className={`streamlit-status status-text-${row.status.toLowerCase()}`}>{row.status}</span></td>
          </tr>)}
          {!filtered.length && <tr><td colSpan={5} className="empty-table">Tidak ada field yang sesuai pencarian atau filter.</td></tr>}
        </tbody></table>
      </div>
      <StreamlitDetails section={section} filter={filter} search={search} />
      <div className="table-footer"><span>Pilih field untuk detail atau Lihat Bukti untuk sumber.</span><span>{filtered.length} dari {section.rows.length} field</span></div>
    </div>}
  </div>;
}

function DetailPanel({ selected, close, openRelated, openEvidence }: { selected: { row: MatchRow; section: MatchSection } | null; close: () => void; openRelated: (category: CategoryId) => void; openEvidence: (documentId:string,page?:number) => void }) {
  if (!selected) return null;
  const { row, section } = selected;
  return <><button className="detail-backdrop" type="button" aria-label="Tutup detail" onClick={close} />
    <aside className="detail-panel" role="dialog" aria-modal="true" aria-label="Detail matching">
      <div className="detail-panel-header"><span className="eyebrow">DETAIL BUKTI</span><button className="icon-button" onClick={close} aria-label="Tutup"><X size={20} /></button></div>
      <h3>{row.field}</h3><p className="detail-origin">{matchingSectionTitle(section)}</p><ScoreBadge status={row.status} />
      <div className="detail-divider" />
      <DataPair label="Acuan dari formulir" value={row.expected} />
      <DataPair label="Hasil pembacaan dokumen" value={row.observed} />
      <DataPair label="Kemiripan karakter / skor field" value={row.score === null ? 'Tidak tersedia' : `${row.score.toFixed(1)}%`} />
      <DataPair label="Halaman bukti" value={row.page ? `Halaman ${row.page}` : 'Tidak dicatat pada hasil pemeriksaan'} />
      {row.note && <div className="detail-note"><Info size={17} />{row.note.replaceAll('v43_address_components', 'Alamat dibandingkan berdasarkan komponen alamat yang terbaca pada dokumen.')}</div>}
      <div className="detail-divider" />
      {row.document_id && row.detail?.type === 'approval' && <ApprovalEvidence row={row}/>}
      {row.document_id && row.detail?.type !== 'approval' && <button className="button button-soft button-full" type="button" onClick={() => openEvidence(row.document_id!,row.page)}><ExternalLink size={16}/> Buka PDF sumber {row.page ? `· Halaman ${row.page}` : ''}</button>}
      <p className="detail-disclaimer">Nilai dibaca dari dokumen yang diunggah. Status MATCH tidak menyatakan keabsahan izin atau tanda tangan.</p>
      <button className="button button-primary button-full" type="button" onClick={() => { close(); openRelated(section.category); }}><FolderOpen size={17} /> Lihat dokumen kategori ini</button>
    </aside>
  </>;
}

function EmptyDocuments({ goUpload }: { goUpload: () => void }) {
  return <div className="empty-documents"><span className="empty-illustration"><FolderOpen size={34} /></span><h3>Belum ada dokumen diunggah</h3>
    <p>File yang sudah dikirim lewat Mulai Analisis tersimpan privat di server dan dapat dibuka kembali pada sesi ini.</p>
    <button className="button button-soft" onClick={goUpload}><UploadCloud size={17} /> Tambah dokumen</button>
  </div>;
}

function App() {
  const [active, setActive] = useState<PageId>('ringkasan');
  const [applicationId,setApplicationId] = useState<string|null>(sessionStorage.getItem('bapeten_application_id'));
  const [result,setResult] = useState<AnalysisResult|null>(null);
  const [job,setJob] = useState<AnalysisJob|null>(null);
  const [working,setWorking] = useState(Boolean(applicationId));
  const [reconnecting, setReconnecting] = useState(false);
  const submitting = useRef(false);
  const monitorController = useRef<AbortController | null>(null);
  useEffect(() => () => monitorController.current?.abort(), []);
  const [savingCategory, setSavingCategory] = useState(false);
  const categorySaveLock = useRef(false);
  const [syncCount,setSyncCount] = useState(0);
  const [syncTotal, setSyncTotal] = useState(0);
  const [analysisStage, setAnalysisStage] = useState<'restoring' | 'preparing' | 'uploading' | 'processing'>('restoring');
  const [backendError,setBackendError] = useState('');
  const displayForm = result?.form_reference ?? null;
  const displaySections = useMemo(() => sortMatchingSections(result?.matching_sections ?? []), [result]);
  const [mobileNav, setMobileNav] = useState(false);
  const [items, setItems] = useState<UploadItem[]>([]);
  const [showUnclassified, setShowUnclassified] = useState(false);
  const [manualCategory, setManualCategory] = useState('');
  const [uploadSearch, setUploadSearch] = useState('');
  const [dragged, setDragged] = useState(false);
  const [toast, setToast] = useState<Toast>(null);
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<Filter>('ALL');
  const [selectedDetail, setSelectedDetail] = useState<{ row: MatchRow; section: MatchSection } | null>(null);
  const [docSearch, setDocSearch] = useState('');
  const [formOpen, setFormOpen] = useState({ facility: true, personnel: true, equipment: true });
  const formNeedsReview = useMemo(() => {
    const missing = (value?: string) => !value?.trim() || ['—', '-'].includes(value.trim());
    return {
      facility: Boolean(displayForm && (missing(displayForm.facility) || missing(displayForm.address))),
      personnel: Boolean(displayForm && (!displayForm.personnel.length || displayForm.personnel.some(p => missing(p.name) || missing(p.role)))),
      equipment: Boolean(displayForm && (!displayForm.equipment.length || displayForm.equipment.some(e => [e.merk_unit, e.tipe_unit, e.nomor_seri_unit, e.merk_tabung, e.tipe_tabung, e.nomor_seri_tabung].some(missing)))),
    };
  }, [displayForm]);
  useEffect(() => {
    setFormOpen({ facility: true, personnel: true, equipment: true });
  }, [formNeedsReview]);
  const toggleForm = (section: keyof typeof formOpen) => setFormOpen(previous => ({ ...previous, [section]: !previous[section] }));
  const reviewBadge = (needsReview: boolean) => needsReview ? <span className="form-review-badge">Perlu diperiksa</span> : undefined;
  const globalInput = useRef<HTMLInputElement>(null);
  const resetDialog = useRef<HTMLDialogElement>(null);
  const manualDialog = useRef<HTMLDialogElement>(null);
  const manualInput = useRef<HTMLInputElement>(null);
  const toastRef = useRef<number | null>(null);
  const totals = useMemo(() => matchingTotals(displaySections), [displaySections]);
  const filterTotals = useMemo(() => matchingTotals(displaySections.map(section => ({
    ...section, rows: section.rows.filter(row => rowMatchesFilter(row, 'ALL', query)),
  }))), [displaySections, query]);
  // Hide entire document panels that have no rows for the selected filter.
  const visibleMatchingSections = useMemo(() => displaySections.filter(section =>
    section.rows.some(row => rowMatchesFilter(row, filter, query))), [displaySections, filter, query]);
  const categoryCount = useMemo(() => new Set(items.filter(f => f.category !== 'unknown').map(f => f.category)).size, [items]);
  const analysisMessage = analysisBlocker(items);
  const unclassifiedCount = items.filter(item => item.category === 'unknown' && !item.isClassifying).length;
  const recognizingCount = items.filter(item => item.isClassifying).length;
  const reviewItems = useMemo(() => {
    const unclassified = items.filter(item => item.category === 'unknown' && !item.isClassifying);
    const visible = showUnclassified && unclassified.length ? unclassified : [
      ...unclassified, ...items.filter(item => item.isClassifying),
      ...items.filter(item => item.category !== 'unknown' && !item.isClassifying),
    ];
    const search = uploadSearch.trim().toLowerCase();
    return visible.filter(item => `${item.name} ${categoryById(item.category)?.name ?? ''} ${item.subtype ?? ''}`.toLowerCase().includes(search));
  }, [items, showUnclassified, uploadSearch]);
  useEffect(() => {
    if (unclassifiedCount === 0) setShowUnclassified(false);
  }, [unclassifiedCount]);
  const formCount = useMemo(() => items.filter((f) => f.category === 'formulir').length, [items]);
  const progressTitle = analysisStage === 'restoring' ? 'Memulihkan sesi evaluasi…' : 'Analisis sedang berjalan…';
  const progressMessage = reconnecting ? 'Koneksi terputus. Mencoba tersambung kembali…'
    : analysisStage === 'restoring' ? 'Memeriksa dokumen dan status analisis terakhir.'
    : analysisStage === 'preparing' ? 'Menyiapkan pengiriman dokumen…'
    : analysisStage === 'uploading' ? `Mengirim dokumen ${syncCount} dari ${syncTotal}…`
    : job?.status === 'completed' ? 'Menyiapkan hasil matching…'
    : job?.message || 'Memulai analisis dokumen…';
  const analysisProgress = job ? Math.max(0, Math.min(100, job.progress)) : undefined;

  useEffect(() => () => { if (toastRef.current !== null) window.clearTimeout(toastRef.current); }, []);
  const announce = useCallback((tone: 'success' | 'warning' | 'info', message: string) => {
    setToast({ tone, message });
    if (toastRef.current !== null) window.clearTimeout(toastRef.current);
    toastRef.current = window.setTimeout(() => setToast(null), 4600);
  }, []);

  const goTo = useCallback((id: PageId) => {
    setActive(id);
    window.scrollTo({top:0,behavior:'smooth'});
  }, []);


  const followAnalysis = useCallback((aid: string, initial: AnalysisJob, signal: AbortSignal) =>
    monitorAnalysis(initial, {
      signal, readJob: () => jobStatus(aid, initial.id, signal),
      readResult: () => jobResults(aid, initial.id, signal),
      onJob: setJob, onConnection: setReconnecting,
    }), []);

  useEffect(() => {
    if (!applicationId || submitting.current) return;
    const aid = applicationId;
    const controller = new AbortController();
    monitorController.current = controller;
    const { signal } = controller;
    setWorking(true);
    setAnalysisStage('restoring');
    setBackendError('');
    goTo('matching');
    const read = <T,>(fn: () => Promise<T>) => retryRead(fn, signal, setReconnecting);
    void (async () => {
      const r = await read(() => listFiles(aid, signal));
      setItems(old => {
        const ids = new Set(old.map(f => f.serverId));
        return [...old, ...r.documents.filter(d => !ids.has(d.id)).map(d => ({
          id: d.id, serverId: d.id, name: d.filename, size: d.size, category: d.category,
          subtype: d.subtype, sha256: d.sha256, addedAt: new Date(d.uploaded * 1000).toISOString(),
        }))];
      });
      const { job: latest } = await read(() => latestJob(aid, signal));
      if (!latest) return;
      setAnalysisStage('processing');
      setResult(null);
      const analyzed = await followAnalysis(aid, latest, signal).catch(error => {
        // An already completed result can be invalidated by a category correction.
        if (latest.status === 'completed' && error?.status === 404) return null;
        throw error;
      });
      if (!analyzed) return;
      const fingerprint = (pairs: string[][]) => JSON.stringify([...pairs].sort((a,b) => a[0].localeCompare(b[0])));
      if (fingerprint(analyzed.document_fingerprint) === fingerprint(r.documents.map(d => [d.id, d.sha256]))) {
        setResult(analyzed);
      }
    })().catch(error => {
      if (signal.aborted) return;
      setBackendError(error instanceof Error ? error.message : 'Gagal memulihkan status analisis');
    }).finally(() => {
      if (!signal.aborted) { setWorking(false); setReconnecting(false); }
    });
    return () => controller.abort();
  }, [applicationId, followAnalysis, goTo]);

  const runAnalysis = async () => {
    if(working || submitting.current || categorySaveLock.current) return;
    if(analysisMessage) {announce('warning', analysisMessage);goTo('upload');return;}
    submitting.current = true;
    monitorController.current?.abort();
    const controller = new AbortController();
    monitorController.current = controller;
    setBackendError('');setWorking(true);setResult(null);setJob(null);setReconnecting(false);
    setAnalysisStage('preparing');setSyncCount(0);setSyncTotal(0);
    setToast(null);setQuery('');setFilter('ALL');setSelectedDetail(null);
    goTo('matching');
    try {
      let aid=applicationId;
      if(!aid){const data=await newApplication();aid=data.application_id;setApplicationId(aid);sessionStorage.setItem('bapeten_application_id',aid);}
      const pending=items.filter((x)=>!x.serverId);
      setSyncTotal(pending.length);
      for(let i=0;i<pending.length;i++) {
        const item=pending[i];
        if(item.category === 'unknown') throw new Error('Pilih kategori untuk semua dokumen terlebih dahulu.');
        if(!item.file) throw new Error('File lokal telah hilang. Tambahkan ulang dokumen.');
        setSyncCount(i+1);
        setAnalysisStage('uploading');
        const uploaded=await uploadFile(aid,item.category,item.file,item.subtype);
        setItems((old)=>old.map((x)=>x.id===item.id?{...x,serverId:uploaded.document.id,sha256:uploaded.document.sha256}:x));
      }
      setAnalysisStage('processing');setSyncCount(0);
      const started=await analyze(aid);
      const initial: AnalysisJob = {id:started.job_id,status:'queued',progress:0,message:'Menunggu antrean analisis',error:null};
      const analyzed = await followAnalysis(aid, initial, controller.signal);
      setResult(analyzed);
      if(analyzed.errors?.length)announce('warning',`${analyzed.errors.length} dokumen gagal dianalisis. Lihat rincian pada halaman Hasil Matching.`);
      else announce('success','Analisis selesai. Hasil verifikasi dokumen berhasil diperbarui.');
    } catch(e) {
      if (controller.signal.aborted) return;
      const message=e instanceof Error?e.message:'Gagal menjalankan analisis';
      setBackendError(message);announce('warning',message);
    } finally {submitting.current=false;if (!controller.signal.aborted) {setWorking(false);setSyncCount(0);setReconnecting(false);}}
  };
  const resetApplication = () => {
    if(working || categorySaveLock.current)return;
    resetDialog.current?.close();
    sessionStorage.removeItem('bapeten_application_id');setApplicationId(null);setItems([]);setResult(null);setJob(null);setBackendError('');setActive('upload');
    setQuery('');setFilter('ALL');setDocSearch('');setUploadSearch('');setManualCategory('');setShowUnclassified(false);setSelectedDetail(null);setToast(null);
  };
  const addFiles = useCallback((category: CategoryId, files: FileList | File[] | null, subtype?: string) => {
    if (working || categorySaveLock.current || !files || !files.length) return;
    const incoming = Array.from(files);
    const valid = incoming.filter((f) => SUPPORTED_EXTENSIONS.has(f.name.split('.').pop()?.toLowerCase() ?? '') && f.size <= MAX_FILE && f.size > 0);
    const invalid = incoming.length - valid.length;
    if (!valid.length) {
      announce('warning', `${invalid} file ditolak. Gunakan PDF/gambar/DOCX, maksimal 40 MB per file.`);
      return;
    }
    if (valid.every(file => items.some(item => item.name === file.name && item.size === file.size))) {
      announce('warning', 'Berkas sudah ada dalam daftar. Ubah kategori melalui daftar dokumen jika diperlukan.');
      return;
    }
    setResult(null);
    setItems((old) => {
      const next = [...old];
      for (const file of valid) {
        const duplicate = next.some((item) => item.name === file.name && item.size === file.size);
        if (!duplicate) {
          next.push({
            id: ID(),
            name: file.name,
            size: file.size,
            category,
            subtype,
            detectedLayer: 1,
            detectionReason: 'Ditambahkan manual ke kategori',
            addedAt: new Date().toISOString(),
            file,
          });
        }
      }
      return next;
    });
    if (invalid) announce('warning', `${invalid} file ditolak. Gunakan PDF/gambar/DOCX, maksimal 40 MB per file.`);
    else announce('success', `File ditambahkan untuk kategori ${categoryById(category)?.name}.`);
  }, [announce, working, items]);

  const handleBatchFiles = useCallback(async (files: FileList | File[] | null) => {
    if (working || categorySaveLock.current || !files || !files.length) return;
    const incoming = Array.from(files);
    const valid = incoming.filter((f) => SUPPORTED_EXTENSIONS.has(f.name.split('.').pop()?.toLowerCase() ?? '') && f.size <= MAX_FILE && f.size > 0);
    const invalid = incoming.length - valid.length;
    setResult(null);

    const newItems: UploadItem[] = [];
    const pendingLayer2: { item: UploadItem; file: File }[] = [];

    for (const file of valid) {
      const duplicate = [...items, ...newItems].some((item) => item.name === file.name && item.size === file.size);
      if (duplicate) continue;

      const l1 = classifyByFilename(file.name);
      if (l1 && l1.category !== 'unknown') {
        newItems.push({
          id: ID(),
          name: file.name,
          size: file.size,
          category: l1.category,
          subtype: l1.subtype,
          detectedLayer: 1,
          detectionReason: l1.reason,
          isClassifying: false,
          addedAt: new Date().toISOString(),
          file,
        });
      } else {
        const item: UploadItem = {
          id: ID(),
          name: file.name,
          size: file.size,
          category: 'unknown',
          detectedLayer: 0,
          detectionReason: 'Sedang mengenali dokumen…',
          isClassifying: true,
          addedAt: new Date().toISOString(),
          file,
        };
        newItems.push(item);
        pendingLayer2.push({ item, file });
      }
    }

    if (!newItems.length) {
      if (invalid) announce('warning', `${invalid} file ditolak. Format tidak didukung atau melebihi 40 MB.`);
      return;
    }

    setItems((old) => [...old, ...newItems]);
    announce(invalid ? 'warning' : 'info', `${newItems.length} berkas ditambahkan.${invalid ? ` ${invalid} file ditolak karena format atau ukuran tidak sesuai.` : ''}${pendingLayer2.length ? ' Pengenalan isi dokumen sedang berjalan.' : ''}`);

    // Trigger Layer 2 for pending items in background
    for (const { item, file } of pendingLayer2) {
      classifyFile(file).then((res) => {
        setItems((current) => current.map((it) => {
          if (it.id !== item.id) return it;
          return applyClassification(it, res);
        }));
      }).catch(() => {
        setItems((current) => current.map((it) => it.id === item.id ? applyClassification(it, { category: 'unknown', layer: 0, confidence: 0, reason: 'Pengenalan gagal. Silakan pilih kategori secara manual.' }) : it));
      });
    }
  }, [items, announce, working]);

  const updateItemCategory = async (id: string, category: CategoryId, subtype?: string) => {
    if (working || categorySaveLock.current) return;
    const item = items.find(it => it.id === id);
    if (!item) return;
    const actualSubtype = categoryById(category)?.requiresSubtype
      ? (subtype || item.subtype || PERSONNEL_TYPES[0]) : undefined;
    categorySaveLock.current = true;
    setSavingCategory(true);
    try {
      if (item.serverId) {
        if (!applicationId) throw new Error('Permohonan tidak tersedia. Muat ulang halaman.');
        await updateFileCategory(applicationId, item.serverId, category, actualSubtype);
      }
      setItems(old => old.map(it => it.id === id ? {
        ...it, category, subtype: actualSubtype, isClassifying: false,
        detectedLayer: undefined, detectionReason: 'Dipilih manual oleh evaluator',
      } : it));
      setResult(null);
    } catch (error) {
      announce('warning', `Kategori gagal disimpan: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      categorySaveLock.current = false;
      setSavingCategory(false);
    }
  };

  const clearAllFiles = () => {
    if (working || categorySaveLock.current || !items.length) return;
    if (!window.confirm(`Hapus semua ${items.length} dokumen dari permohonan ini?`)) return;
    items.forEach((item) => {
      if (item.serverId && applicationId) {
        deleteFile(applicationId, item.serverId).catch(() => {});
      }
    });
    setItems([]);
    setResult(null);
    announce('info', 'Semua berkas dihapus dari permohonan.');
  };

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragged(false);
    handleBatchFiles(event.dataTransfer.files);
  };
  const removeFile = (id: string) => {
    const item=items.find((x)=>x.id===id);
    if(!item || working || categorySaveLock.current)return;
    if(item.serverId && applicationId)deleteFile(applicationId,item.serverId).catch((e)=>announce('warning',String(e)));
    setItems((prev)=>prev.filter((x)=>x.id!==id));setResult(null);
    announce('info','File dihapus dari daftar. Analisis perlu dijalankan ulang.');
  };
  const openEvidence = (documentId:string,page?:number) => {
    if(!applicationId)return;
    const win=window.open('about:blank','_blank');
    fetchPreviewFile(applicationId,documentId).then((blob)=>{
      const url=URL.createObjectURL(blob);
      if(win)win.location.href=url+(page?`#page=${page}`:'');
      else window.open(url+(page?`#page=${page}`:''),'_blank');
      window.setTimeout(()=>URL.revokeObjectURL(url),120000);
    }).catch((e)=>{win?.close();announce('warning',String(e));});
  };
  const viewFile = (file?: File, serverId?: string) => {
    if(!file){
      if(!applicationId || !serverId){announce('warning','File belum tersedia di server.');return;}
      const win=window.open('about:blank','_blank');
      fetchPreviewFile(applicationId,serverId).then((blob)=>{
        const uri=URL.createObjectURL(blob);
        if(win)win.location.href=uri;else window.open(uri,'_blank');
        window.setTimeout(()=>URL.revokeObjectURL(uri),120000);
      }).catch(e=>{if(win)win.close();announce('warning',String(e));});return;
    }
    const url = URL.createObjectURL(file);
    const win = window.open('about:blank', '_blank');
    if (win) { win.opener = null; win.location.href = url; }
    if (!win) announce('warning', 'Popup diblokir browser. Izinkan popup untuk membuka dokumen.');
    window.setTimeout(() => URL.revokeObjectURL(url), 120000);
  };
  const visibleDocuments = items.filter((item) => `${item.name} ${(categoryById(item.category)?.name ?? 'Perlu Pilih Kategori')} ${item.subtype || ''}`.toLowerCase().includes(docSearch.toLowerCase()));

  return <div className="app-shell">
    <Sidebar active={active} navigate={goTo} open={mobileNav} close={() => setMobileNav(false)} working={working} />
    <main className="main-area">
      <div className="topbar">
        <div className="topbar-left"><button className="mobile-menu icon-button" onClick={() => setMobileNav(true)} aria-label="Buka menu"><Menu size={20}/></button>
          <span className="breadcrumb">Workspace</span><ChevronRight size={15}/><span className="breadcrumb-current">Evaluasi Permohonan</span></div>
        <div className="topbar-right"><span className="demo-indicator"><span/> {working ? 'Analisis Berlangsung' : backendError ? 'Perlu Diperiksa' : result ? 'Hasil Tersedia' : 'Menunggu Analisis'}</span><span className="user-avatar">EV</span><span className="user-label">Evaluator</span></div>
      </div>
      <div className="content-wrap">
        <section className="page-section overview-section" id="ringkasan" hidden={active!=='ringkasan'}>
          <div className="page-hero">
            <div><span className="eyebrow">DASHBOARD · WORKSPACE EVALUASI</span><h1>Evaluasi Dokumen <span>Permohonan</span></h1>
              <div className="hero-scope-subtitle">Radiologi Diagnostik &amp; Intervensional</div>
              <p>Pusat pemeriksaan dokumen, perbandingan data formulir, dan penelusuran hasil matching per kategori.</p></div>
            <div className="hero-actions"><button className="button button-new-evaluation hero-button" disabled={working || savingCategory} onClick={() => resetDialog.current?.showModal()}><RotateCcw size={17} aria-hidden="true"/>Mulai Evaluasi Baru</button><button className="button button-primary hero-button" onClick={() => goTo('upload')}>Upload Dokumen <ArrowRight size={17}/></button></div>
          </div>
          <div className="summary-grid">
            <SummaryCard icon={<FolderOpen size={25}/>} label="Dokumen di permohonan" value={items.length} note={`${categoryCount} dari ${CATEGORIES.length} kategori terisi`} tone="rose" />
            <SummaryCard icon={<CheckCircle2 size={25}/>} label="Field MATCH" value={totals.match} note={`${totals.percentage.toFixed(1)}% dari ${totals.total} field yang dianalisis`} tone="green" />
            <SummaryCard icon={<FileClock size={25}/>} label="Perlu Review" value={totals.review} note="Belum terkonfirmasi di sumber" tone="amber" />
            <SummaryCard icon={<AlertCircle size={25}/>} label="Mismatch" value={totals.mismatch} note="Perbedaan identitas yang terdeteksi" tone="red" />
          </div>
          <div className="overview-banner"><div className="overview-banner-icon"><Info size={19}/></div>
            <p><strong>{result ? 'Hasil evaluasi dokumen tersedia.' : 'Belum ada hasil analisis.'}</strong> {result ? `${result.analyzed_documents} dokumen dianalisis; ${result.errors.length} gagal. Field REVIEW memerlukan pemeriksaan evaluator.` : 'Unggah dokumen melalui menu Upload Dokumen, lalu klik Mulai Analisis. Ringkasan hasil akan muncul di sini setelah analisis selesai.'}</p>
            {result && <button className="text-action" onClick={() => goTo('matching')}>Lihat hasil analisis <ArrowRight size={15}/></button>}
          </div>
        </section>

        <section className="page-section" id="upload" hidden={active!=='upload'}>
          <SectionHeading
            eyebrow="LANGKAH 01"
            title="Upload Dokumen Permohonan"
            description="Unggah berkas, periksa kategori, lalu mulai analisis."
          />
          <div className="surface upload-surface">
            <div
              className={`dropzone ${items.length ? 'dropzone-compact' : ''} ${dragged ? 'drag-active' : ''}`}
              onDragOver={(e) => { e.preventDefault(); setDragged(true); }}
              onDragLeave={(e) => { e.preventDefault(); setDragged(false); }}
              onDrop={onDrop}
            >
              <div className="dropzone-icon"><CloudUpload size={33}/></div>
              <div className="dropzone-copy">
                <h3>{items.length ? 'Tambahkan berkas permohonan' : 'Unggah berkas permohonan'}</h3>
                <p>{items.length ? 'PDF, JPG, PNG, DOCX · Maks. 40 MB/file' : 'Tarik berkas ke sini atau pilih dari komputer. Kategori akan dikenali otomatis.'}</p>
              </div>
              <div className="dropzone-actions">
                <button className="button button-primary" type="button" disabled={working || savingCategory} onClick={() => globalInput.current?.click()}>
                  <UploadCloud size={17}/> Pilih Berkas
                </button>
                <button className="button button-new-evaluation" type="button" disabled={working || savingCategory} onClick={() => { setManualCategory(''); manualDialog.current?.showModal(); }}>
                  <FolderOpen size={17}/> Tambah ke Kategori
                </button>
              </div>
              <input
                ref={globalInput}
                type="file"
                multiple
                accept=".pdf,.jpg,.jpeg,.png,.bmp,.webp,.tif,.tiff,.docx"
                hidden
                onChange={(event) => { handleBatchFiles(event.target.files); event.target.value = ''; }}
              />
              {!items.length && <small>PDF, JPG, PNG, DOCX · Maks. 40 MB/file</small>}
            </div>

            {items.length > 0 && (
              <div className="batch-review-section">
                <div className="batch-summary-header">
                  <div className="batch-summary-left">
                    <div className="batch-heading"><h4>Daftar Dokumen</h4><span>{items.length} dokumen · {categoryCount} kategori</span></div>
                    {formCount === 1 ? (
                      <span className="status-pill success"><CheckCircle2 size={14} /> 1 Formulir Permohonan</span>
                    ) : formCount === 0 ? (
                      <span className="status-pill danger"><AlertCircle size={14} /> Formulir belum tersedia</span>
                    ) : (
                      <span className="status-pill warning"><AlertCircle size={14} /> Terdeteksi {formCount} Formulir (Wajib tepat 1)</span>
                    )}
                    {recognizingCount > 0 && <span className="tiny-counter" role="status">Mengenali {recognizingCount} dokumen…</span>}
                  </div>
                  <button className="text-action" type="button" disabled={working || savingCategory} onClick={clearAllFiles}>
                    <Trash2 size={14} /> Kosongkan
                  </button>
                </div>

                <div className="upload-toolbar">
                <div className="upload-filters" role="group" aria-label="Filter klasifikasi dokumen">
                  <button type="button" aria-pressed={!showUnclassified} onClick={() => setShowUnclassified(false)}>
                    Semua ({items.length})
                  </button>
                  {unclassifiedCount > 0 && <button type="button" className="unclassified-filter" aria-pressed={showUnclassified} onClick={() => setShowUnclassified(true)}>
                    <AlertCircle size={14} aria-hidden="true" /> Perlu Pilih Kategori ({unclassifiedCount})
                  </button>}
                </div>
                <label className="search-field"><Search size={17}/><input type="search" aria-label="Cari dokumen unggahan" placeholder="Cari dokumen…" value={uploadSearch} onChange={event => setUploadSearch(event.target.value)} /></label>
                </div>
                <div className="batch-table-wrapper">
                  <div className="table-scroll">
                    <table className="batch-table">
                      <thead>
                        <tr>
                          <th className="batch-th-doc">Dokumen</th>
                          <th className="batch-th-category">Kategori Dokumen</th>
                          <th className="batch-th-action">Aksi</th>
                        </tr>
                      </thead>
                      <tbody>
                        {reviewItems.map((item) => {
                          const currentVal = item.category === 'personel'
                            ? `personel:${item.subtype || PERSONNEL_TYPES[0]}`
                            : item.category;

                          const isCustomSubtype = item.category === 'personel' &&
                            Boolean(item.subtype) &&
                            !(PERSONNEL_TYPES as readonly string[]).includes(item.subtype!);

                          return (
                            <tr key={item.id} className={item.category === 'unknown' && !item.isClassifying ? 'unclassified-row' : undefined}>
                              <td className="batch-td-doc">
                                <div className="batch-file-info">
                                  <span className={`category-icon category-${item.category} batch-file-icon`}>
                                    <Glyph name={categoryById(item.category)?.icon ?? 'file'} />
                                  </span>
                                  <div className="batch-file-text">
                                    <div className="batch-file-name" title={item.name}>{item.name}</div>
                                    <span className="batch-file-size">{sizeLabel(item.size)}</span>
                                  </div>
                                </div>
                              </td>
                              <td className="batch-td-category">
                                <select
                                  className="table-category-select"
                                  aria-label={`Kategori ${item.name}`}
                                  disabled={working || savingCategory}
                                  value={currentVal}
                                  onChange={(e) => {
                                    const val = e.target.value;
                                    if (val.startsWith('personel:')) {
                                      updateItemCategory(item.id, 'personel', val.slice('personel:'.length));
                                    } else {
                                      updateItemCategory(item.id, val as CategoryId);
                                    }
                                  }}
                                >
                                  {item.category === 'unknown' && <option value="unknown" disabled>{item.isClassifying ? 'Mengenali…' : 'Perlu Pilih Kategori'}</option>}
                                  {CATEGORIES.map((c) => {
                                    if (c.id === 'personel') {
                                      return (
                                        <optgroup key="personel-group" label="Dokumen Personel">
                                          {PERSONNEL_TYPES.map((t) => (
                                            <option key={`personel:${t}`} value={`personel:${t}`}>
                                              Personel: {t}
                                            </option>
                                          ))}
                                          {isCustomSubtype && (
                                            <option key={`personel:${item.subtype}`} value={`personel:${item.subtype}`}>
                                              Personel: {item.subtype}
                                            </option>
                                          )}
                                        </optgroup>
                                      );
                                    }
                                    return (
                                      <option key={c.id} value={c.id}>{c.name}</option>
                                    );
                                  })}
                                </select>
                              </td>
                              <td className="batch-td-action">
                                <div className="batch-file-actions">
                                <button className="button button-soft button-sm" type="button" onClick={() => viewFile(item.file, item.serverId)} aria-label={`Lihat ${item.name}`}>
                                  <Eye size={16} aria-hidden="true"/> Lihat
                                </button>
                                <button
                                  className="icon-button delete-icon"
                                  type="button"
                                  disabled={working || savingCategory}
                                  onClick={() => removeFile(item.id)}
                                  aria-label={`Hapus ${item.name}`}
                                  title="Hapus berkas"
                                >
                                  <Trash2 size={16} />
                                </button>
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                        {!reviewItems.length && <tr><td colSpan={3} className="upload-no-results">Tidak ada dokumen yang cocok dengan pencarian.</td></tr>}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            )}

            {items.length > 0 && (
              <div className="classification-disclaimer">
                <AlertCircle size={16} />
                <span>
                  <strong>Catatan Evaluator:</strong> Periksa kembali kategori setiap dokumen sebelum memulai analisis.
                </span>
              </div>
            )}

            <div className={`analysis-action-bar ${analysisMessage && !working ? 'analysis-blocked' : ''}`}>
              <div className="analysis-readiness" role="status">
                {working ? <Activity size={22}/> : analysisMessage ? <AlertCircle size={22}/> : <CheckCircle2 size={22}/>}
                <div>
                  <strong>{working ? progressMessage : savingCategory ? 'Menyimpan kategori…' : analysisMessage || 'Dokumen siap dianalisis'}</strong>
                  {!working && !analysisMessage && <small>Data dokumen akan dicocokkan dengan Formulir Permohonan.</small>}
                </div>
              </div>
              <button className="button button-primary" type="button" disabled={working || savingCategory || Boolean(analysisMessage)} onClick={runAnalysis}>
                <Activity size={17}/>
                {working ? `Memproses... ${syncCount ? `unggah ${syncCount}` : `${job?.progress ?? 0}%`}` : 'Mulai Analisis'}
              </button>
            </div>

          </div>
        </section>

        <section className="page-section" id="formulir" hidden={active!=='formulir'}>
          <SectionHeading eyebrow="LANGKAH 02" title="Formulir Permohonan" description="Ringkasan data acuan untuk mencocokkan informasi pada dokumen pendukung." action={<span className="outline-label"><Info size={14}/>{displayForm ? "Data tersedia" : "Belum dianalisis"}</span>} />
          <div className="form-overview-grid"><div className="form-stat"><span className="form-stat-icon tone-blue"><UsersRound size={25}/></span><div><small>Total Personel</small><strong>{(displayForm?.personnel.length ?? 0)}</strong><span>Data formulir</span></div></div>
            <div className="form-stat"><span className="form-stat-icon tone-green"><Layers3 size={25}/></span><div><small>Total Peralatan</small><strong>{(displayForm?.equipment.length ?? 0)}</strong><span>Pesawat sinar-X</span></div></div></div>
          {Object.values(formNeedsReview).some(Boolean) && <div className="form-controls">
            <span>Data belum lengkap terbaca. Periksa kembali dengan dokumen formulir.</span>
          </div>}
          <div className="surface form-surface">
            <Accordion title="Informasi Instansi" icon={<Home size={20}/>} open={formOpen.facility} onToggle={() => toggleForm('facility')} count={reviewBadge(formNeedsReview.facility)}>
              <div className="facility-info"><DataPair label="Nama fasilitas" value={displayForm?.facility || 'Belum ada hasil formulir'}/><DataPair label="Alamat proyek" value={displayForm?.address || '—'}/></div>
            </Accordion>
            <Accordion title="Data Personel" icon={<UsersRound size={20}/>} open={formOpen.personnel} onToggle={() => toggleForm('personnel')} count={reviewBadge(formNeedsReview.personnel)}>
              {!displayForm?.personnel.length && <p>{displayForm ? 'Data personel belum terbaca. Periksa dokumen formulir.' : 'Belum ada hasil analisis formulir.'}</p>}
              <div className="list-data">{(displayForm?.personnel ?? []).map((p, i) => <div key={`${p.name}-${i}`} className="list-data-row"><span className="numbered">{i + 1}</span><div><strong>{p.name}</strong><small>{p.role?.trim() ? `Keahlian: ${p.role}` : 'Keahlian tidak tercantum dalam formulir'}</small></div></div>)}</div>
            </Accordion>
            <Accordion title="Data Peralatan" icon={<Layers3 size={20}/>} open={formOpen.equipment} onToggle={() => toggleForm('equipment')} count={reviewBadge(formNeedsReview.equipment)}>
              {!displayForm?.equipment.length && <p>{displayForm ? 'Data peralatan belum terbaca. Periksa dokumen formulir.' : 'Belum ada hasil analisis formulir.'}</p>}
              <div className="equipments-grid">{(displayForm?.equipment ?? []).map((e) => <article key={e.label} className="equipment-card"><div className="equipment-head"><strong>{e.label}</strong><span>{e.tipe_unit}</span></div>
                <DataPair label="Merek unit" value={e.merk_unit}/><DataPair label="Nomor seri unit" value={e.nomor_seri_unit}/><DataPair label="Merek tabung" value={e.merk_tabung}/><DataPair label="Tipe tabung" value={e.tipe_tabung}/><DataPair label="Nomor seri insersi tabung" value={e.nomor_seri_tabung}/>
              </article>)}</div>
            </Accordion>
          </div>
        </section>

        <section className="page-section" id="matching" hidden={active!=='matching'}>
          <SectionHeading eyebrow="LANGKAH 03" title="Hasil Matching" description="Perbandingan data Formulir dan Dokumen, dengan status MATCH, REVIEW, atau MISMATCH per field." action={result ? <span className="outline-label"><FileCheck2 size={14}/> {result.analyzed_documents} dokumen dianalisis</span> : undefined} />
          <div className="surface matching-surface">
            {result && <div className="matching-toolbar"><div className="match-toolbar-summary"><strong>Hasil Validasi Dokumen</strong><p>{`Selesai dianalisis pada ${analysisDateLabel(result.finished_at)}`}</p></div><div className="filter-group">
              <label className="search-field"><Search size={17}/><input type="search" placeholder="Cari field atau nilai..." value={query} onChange={(e) => setQuery(e.target.value)} /></label>
              <div className="filter-buttons" role="group" aria-label="Filter status">{(['ALL','MATCH','REVIEW','MISMATCH'] as Filter[]).map((f) => <button key={f} className={filter === f ? 'active' : ''} aria-pressed={filter === f} onClick={() => setFilter(f)}>{f === 'ALL' ? 'Semua' : f === 'MATCH' ? 'Match' : f === 'REVIEW' ? 'Review' : 'Mismatch'} ({f === 'ALL' ? filterTotals.total : f === 'MATCH' ? filterTotals.match : f === 'REVIEW' ? filterTotals.review : filterTotals.mismatch})</button>)}</div>
            </div></div>}
            {working && <div className="analysis-progress">
              <div className="analysis-progress-heading"><LoaderCircle className="analysis-spinner" size={28} aria-hidden="true"/><div role="status"><strong>{progressTitle}</strong><p>{progressMessage}</p></div></div>
              <div className={`progress-track ${analysisProgress === undefined ? 'progress-indeterminate' : ''}`} role="progressbar" aria-label={analysisStage === 'uploading' ? 'Pengiriman dokumen' : 'Progres analisis'} aria-valuemin={0} aria-valuemax={100} aria-valuenow={analysisProgress} aria-valuetext={progressMessage}><span style={analysisProgress === undefined ? undefined : {width:`${analysisProgress}%`}}/></div>
              {analysisProgress !== undefined && <small>{analysisProgress}%</small>}
              <p className="analysis-progress-hint">Anda dapat membuka menu lain. Proses tetap berjalan.</p>
            </div>}
            {backendError && !working && <div className="analysis-error" role="alert"><AlertCircle size={24}/><div><strong>Analisis belum berhasil diselesaikan</strong><p>{backendError}</p><button className="button button-soft" type="button" onClick={() => goTo('upload')}>Kembali ke Upload</button></div></div>}
            {result?.warnings?.length ? <div className="analysis-errors"><strong>Peringatan parser formulir</strong>{result.warnings.map((e,i)=><p key={i}>{e}</p>)}</div> : null}
            {result?.errors?.length ? <div className="analysis-errors"><strong>{result.errors.length} dokumen gagal diekstrak</strong>{result.errors.map((e,idx)=><p key={`${e.document_id}-${idx}`}>{e.filename}: {e.error}</p>)}</div>:null}
            {!working && !result && !backendError && <div className="analysis-empty"><Activity size={35}/><strong>Belum ada hasil matching</strong><p>Unggah berkas permohonan, kemudian klik Mulai Analisis untuk melihat hasil verifikasi dokumen.</p><button className="button button-soft" onClick={()=>goTo('upload')}>Ke halaman Upload</button></div>}
            <div className="matching-sections">
              {visibleMatchingSections.map((s, i) => <MatchingSection key={`${filter}:${s.id}`} section={s} search={query} filter={filter} onRowClick={(row, section) => setSelectedDetail({row, section})} expandedByDefault={i === 0} />)}
              {result && visibleMatchingSections.length === 0 && <div className="matching-filter-empty">Tidak ada field dengan status atau kata kunci yang dipilih.</div>}
            </div>
            <div className="matching-footer"><CircleHelp size={18}/><span>Status adalah hasil pencocokan data, <strong>bukan keputusan izin</strong>. Bukti pengesahan tetap memerlukan pemeriksaan evaluator.</span></div>
          </div>
        </section>

        <section className="page-section documents-section" id="dokumen" hidden={active!=='dokumen'}>
          <SectionHeading eyebrow="LANGKAH 04" title="Dokumen yang Diunggah" description="Daftar berkas untuk permohonan aktif; berkas yang terkirim disimpan di server secara privat." action={<span className="tiny-counter">{items.length} file</span>} />
          <div className="surface documents-surface">
            {items.length > 0 && <div className="documents-toolbar"><label className="search-field"><Search size={17}/><input type="search" value={docSearch} onChange={(e) => setDocSearch(e.target.value)} placeholder="Cari nama atau kategori dokumen..." /></label><span>{visibleDocuments.length} file ditampilkan</span></div>}
            {items.length === 0 ? <EmptyDocuments goUpload={() => goTo('upload')}/> : <div className="documents-grid">{visibleDocuments.map((item) => <article className="document-card" key={item.id}>
              <div className="document-card-top"><span className={`document-file-icon category-${item.category}`}><FileText size={25}/></span><button className="icon-button" aria-label={`Hapus ${item.name}`} title="Hapus dari daftar sementara" onClick={() => removeFile(item.id)}><Trash2 size={17}/></button></div>
              <strong title={item.name}>{item.name}</strong><span className="document-type">{item.name.split('.').at(-1)?.toUpperCase()} · {sizeLabel(item.size)}</span>
              <div className="document-meta"><span>{(categoryById(item.category)?.name ?? 'Perlu Pilih Kategori')}</span>{item.subtype && <small>{item.subtype}</small>}</div>
              <div className="document-card-footer"><span><CalendarDays size={13}/>{dateLabel(item.addedAt)}</span><button className="open-file" onClick={() => viewFile(item.file,item.serverId)}><ExternalLink size={15}/> Buka</button></div>
            </article>)}{!visibleDocuments.length && <p className="doc-no-results">Tidak ada dokumen yang cocok dengan pencarian.</p>}</div>}
          </div>
        </section>
      </div>
    </main>
    <dialog ref={manualDialog} className="reset-dialog manual-upload-dialog" aria-labelledby="manual-upload-title" aria-describedby="manual-upload-description">
      <h2 id="manual-upload-title">Tambah ke Kategori</h2>
      <p id="manual-upload-description">Pilih kategori, lalu tambahkan berkas ke daftar dokumen.</p>
      <label className="manual-category-label" htmlFor="manual-category">Kategori Dokumen</label>
      <select id="manual-category" className="table-category-select" autoFocus value={manualCategory} disabled={working || savingCategory} onChange={event => setManualCategory(event.target.value)}>
        <option value="" disabled>Pilih kategori</option>
        {CATEGORIES.map(category => category.requiresSubtype ? (
          <optgroup key={category.id} label={category.name}>
            {PERSONNEL_TYPES.map(subtype => <option key={subtype} value={`personel:${subtype}`}>Personel: {subtype}</option>)}
          </optgroup>
        ) : <option key={category.id} value={category.id}>{category.name}</option>)}
      </select>
      <input ref={manualInput} hidden type="file" multiple accept=".pdf,.jpg,.jpeg,.png,.bmp,.webp,.tif,.tiff,.docx" onChange={event => {
        if (event.target.files?.length && manualCategory) {
          const isPersonnel = manualCategory.startsWith('personel:');
          addFiles(isPersonnel ? 'personel' : manualCategory as CategoryId, event.target.files, isPersonnel ? manualCategory.slice('personel:'.length) : undefined);
          manualDialog.current?.close();
          setShowUnclassified(false);setUploadSearch('');
        }
        event.target.value = '';
      }}/>
      <div className="reset-dialog-actions">
        <button className="button button-soft" type="button" onClick={() => manualDialog.current?.close()}>Batal</button>
        <button className="button button-primary" type="button" disabled={!manualCategory || working || savingCategory} onClick={() => manualInput.current?.click()}><UploadCloud size={17}/> Pilih Berkas</button>
      </div>
    </dialog>
    <dialog ref={resetDialog} className="reset-dialog" aria-labelledby="reset-dialog-title" aria-describedby="reset-dialog-description">
      <h2 id="reset-dialog-title">Mulai evaluasi baru?</h2>
      <p id="reset-dialog-description">Data unggahan dan hasil analisis pada sesi ini akan dikosongkan untuk memulai evaluasi instansi berikutnya.</p>
      <div className="reset-dialog-actions">
        <button className="button button-soft" autoFocus onClick={() => resetDialog.current?.close()}>Batal</button>
        <button className="button button-primary" disabled={working || savingCategory} onClick={resetApplication}>Mulai Evaluasi Baru</button>
      </div>
    </dialog>
    <DetailPanel selected={selectedDetail} close={() => setSelectedDetail(null)} openEvidence={openEvidence} openRelated={(category) => { goTo('dokumen'); announce('info', `Cari dokumen kategori ${categoryById(category)?.name} pada daftar file yang diunggah.`); }} />
    {toast && <div className={`toast toast-${toast.tone}`} role="status"><span className="toast-icon">{toast.tone === 'success' ? <Check size={18}/> : toast.tone === 'warning' ? <AlertCircle size={18}/> : <Info size={18}/>}</span><p>{toast.message}</p><button className="icon-button" onClick={() => setToast(null)} aria-label="Tutup pesan"><X size={16}/></button></div>}
  </div>;
}

export default App;
