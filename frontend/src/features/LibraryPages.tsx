import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Download, FileUp, FolderLock, LoaderCircle, Search, Trash2 } from 'lucide-react';
import { useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useToast } from '../components/Toast';
import { EmptyState, ErrorState, LoadingCard, PageTitle, Pagination, StatusBadge } from '../components/ui';
import { api, UserDocument } from '../lib/api';
import { formatBytes, formatDate, formatScore } from '../lib/format';

const PAGE_SIZE = 20;
const MAX_BYTES = 5 * 1024 * 1024;
const ACCEPTED = '.pdf,.txt,.md,application/pdf,text/plain,text/markdown';

function statusTone(status: UserDocument['status']) {
  return status === 'ready' ? 'ok' : status === 'failed' ? 'error' : 'warn';
}

function useDocumentActions() {
  const queryClient = useQueryClient();
  const notify = useToast();
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ['library'] });
    void queryClient.invalidateQueries({ queryKey: ['dashboard'] });
  };
  const download = async (document: UserDocument) => {
    try {
      const { blob, filename } = await api.downloadDocument(document.document_id);
      const url = URL.createObjectURL(blob);
      const anchor = window.document.createElement('a');
      anchor.href = url;
      anchor.download = filename;
      anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (caught) {
      notify(caught instanceof Error ? caught.message : 'Download failed', 'error');
    }
  };
  const remove = useMutation({
    mutationFn: (document: UserDocument) => api.deleteDocument(document.document_id),
    onSuccess: (_, document) => {
      notify(`Deleted “${document.title}”.`);
      refresh();
    },
    onError: (caught: Error) => notify(caught.message, 'error'),
  });
  const confirmDelete = (document: UserDocument, onDone?: () => void) => {
    if (window.confirm(`Delete “${document.title}” permanently? This cannot be undone.`)) {
      remove.mutate(document, { onSuccess: onDone });
    }
  };
  return { download, confirmDelete, deleting: remove.isPending, refresh };
}

function UploadForm() {
  const notify = useToast();
  const { refresh } = useDocumentActions();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState('');
  const [error, setError] = useState<string | null>(null);
  const upload = useMutation({
    mutationFn: () => api.uploadDocument(file as File, title),
    onSuccess: (document) => {
      refresh();
      setFile(null);
      setTitle('');
      if (input.current) input.current.value = '';
      if (document.status === 'ready') notify(`Uploaded “${document.title}”.`);
      else notify(`Uploaded “${document.title}”, but text extraction failed: ${document.error}`, 'error');
    },
  });
  const choose = (selected: File | null) => {
    setError(null);
    upload.reset();
    if (selected && selected.size > MAX_BYTES) {
      setError('Files must be 5 MB or smaller.');
      setFile(null);
      return;
    }
    if (selected && !/\.(pdf|txt|md)$/i.test(selected.name)) {
      setError('Upload a PDF, TXT, or Markdown (.md) file.');
      setFile(null);
      return;
    }
    setFile(selected);
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!file) return setError('Choose a file to upload.');
    upload.mutate();
  };
  return (
    <form className="panel upload-form" onSubmit={submit}>
      <div className="panel-heading"><div><span className="section-kicker">UPLOAD</span><h2>Add a document</h2></div></div>
      <label className="file-drop">
        <FileUp size={20} />
        <span>{file ? `${file.name} · ${formatBytes(file.size)}` : 'Choose a PDF, TXT, or Markdown file (max 5 MB)'}</span>
        <input ref={input} type="file" accept={ACCEPTED} onChange={(event) => choose(event.target.files?.[0] ?? null)} />
      </label>
      <label>Title (optional)<input value={title} maxLength={200} onChange={(event) => setTitle(event.target.value)} placeholder="Defaults to the file name" /></label>
      {(error || upload.isError) && <p className="auth-error" role="alert">{error ?? upload.error?.message}</p>}
      <button className="primary-button" disabled={!file || upload.isPending}>{upload.isPending && <LoaderCircle className="spin" size={15} />} Upload</button>
      <small className="field-hint">Only upload documents you are permitted to store. Files are private to your account; contents are checked, not just extensions.</small>
    </form>
  );
}

export function MyDocumentsPage() {
  const [page, setPage] = useState(1);
  const [filter, setFilter] = useState('');
  const [searchText, setSearchText] = useState('');
  const { download, confirmDelete, deleting } = useDocumentActions();
  const list = useQuery({
    queryKey: ['library', filter, page],
    queryFn: () => api.libraryDocuments({ q: filter || undefined, limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE }),
    placeholderData: keepPreviousData,
  });
  const search = useMutation({ mutationFn: (text: string) => api.searchLibrary(text, 10) });
  return (
    <div className="subpage">
      <PageTitle eyebrow="PRIVATE LIBRARY" title="My documents." description="Upload your own legal documents, search inside them, and download or delete them at any time. Only you can see them." />
      <div className="two-column">
        <UploadForm />
        <form className="panel" onSubmit={(event) => { event.preventDefault(); if (searchText.trim()) search.mutate(searchText.trim()); }}>
          <div className="panel-heading"><div><span className="section-kicker">FULL-TEXT SEARCH</span><h2>Search inside my documents</h2></div></div>
          <div className="inline-search"><Search size={16} aria-hidden /><input aria-label="Search inside my documents" value={searchText} maxLength={2000} onChange={(event) => setSearchText(event.target.value)} placeholder="Search terms…" /><button className="primary-button" disabled={!searchText.trim() || search.isPending}>{search.isPending ? <LoaderCircle className="spin" size={14} /> : 'Search'}</button></div>
          {search.isError && <ErrorState message={search.error.message} />}
          {search.data && (
            search.data.hits.length === 0
              ? <p className="field-hint">No matches in {search.data.searched_documents} ready document(s).</p>
              : <ul className="simple-list">{search.data.hits.map((hit) => (
                  <li key={hit.document_id}><Link to={`/library/${hit.document_id}`}>{hit.title}</Link><span>{hit.excerpt}</span><small>BM25 {formatScore(hit.score)}</small></li>
                ))}</ul>
          )}
        </form>
      </div>
      <section className="panel">
        <div className="panel-heading">
          <div><span className="section-kicker">LIBRARY</span><h2>{list.data ? `${list.data.total} document${list.data.total === 1 ? '' : 's'}` : 'Documents'}</h2></div>
          <label className="inline-filter"><Search size={14} /><input aria-label="Filter by title or file name" placeholder="Filter by title or file name" value={filter} maxLength={200} onChange={(event) => { setFilter(event.target.value); setPage(1); }} /></label>
        </div>
        {list.isLoading && <LoadingCard label="Loading your documents…" />}
        {list.isError && <ErrorState message={list.error.message} onRetry={() => void list.refetch()} />}
        {list.data?.documents.length === 0 && <EmptyState icon={<FolderLock size={22} />} title={filter ? 'No documents match that filter.' : 'Your library is empty.'}><p>Uploaded files appear here with their processing status.</p></EmptyState>}
        {Boolean(list.data?.documents.length) && (
          <div className="table-scroll">
            <table className="data-table">
              <thead><tr><th scope="col">Title</th><th scope="col">File</th><th scope="col">Size</th><th scope="col">Status</th><th scope="col">Uploaded</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
              <tbody>
                {list.data?.documents.map((document) => (
                  <tr key={document.document_id}>
                    <td><Link to={`/library/${document.document_id}`}>{document.title}</Link></td>
                    <td>{document.filename}</td>
                    <td>{formatBytes(document.size_bytes)}</td>
                    <td><StatusBadge tone={statusTone(document.status)}>{document.status}</StatusBadge>{document.error && <small className="cell-note">{document.error}</small>}</td>
                    <td>{formatDate(document.created_at, true)}</td>
                    <td className="row-actions">
                      <button type="button" className="text-action" onClick={() => void download(document)} aria-label={`Download ${document.title}`}><Download size={14} /> Download</button>
                      <button type="button" className="text-action danger" disabled={deleting} onClick={() => confirmDelete(document)} aria-label={`Delete ${document.title}`}><Trash2 size={14} /> Delete</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {list.data && <Pagination page={page} pageSize={PAGE_SIZE} total={list.data.total} onPage={setPage} />}
      </section>
    </div>
  );
}

export function MyDocumentPage() {
  const { documentId = '' } = useParams();
  const navigate = useNavigate();
  const { download, confirmDelete, deleting } = useDocumentActions();
  const { data, isLoading, isError, error } = useQuery({ queryKey: ['library', 'document', documentId], queryFn: () => api.libraryDocument(documentId) });
  return (
    <div className="subpage document-page">
      <Link className="back-link" to="/library"><ArrowLeft size={15} /> Back to my documents</Link>
      {isLoading && <LoadingCard label="Opening document…" />}
      {isError && <ErrorState message={error.message} />}
      {data && (
        <>
          <PageTitle
            eyebrow={`PRIVATE DOCUMENT · ${data.status.toUpperCase()}`}
            title={data.title}
            description={`${data.filename} · ${formatBytes(data.size_bytes)}${data.page_count ? ` · ${data.page_count} pages` : ''} · uploaded ${formatDate(data.created_at, true)}`}
            actions={<>
              <button type="button" className="secondary-button" onClick={() => void download(data)}><Download size={14} /> Download</button>
              <button type="button" className="secondary-button danger" disabled={deleting} onClick={() => confirmDelete(data, () => navigate('/library'))}><Trash2 size={14} /> Delete</button>
            </>}
          />
          {data.status === 'failed' && <ErrorState title="Text extraction failed" message={data.error ?? 'Unknown error'} />}
          <dl className="metadata-grid">
            <div><dt>Content type</dt><dd>{data.content_type}</dd></div>
            <div><dt>Extracted characters</dt><dd>{data.char_count.toLocaleString()}</dd></div>
            <div><dt>SHA-256</dt><dd className="mono">{data.sha256}</dd></div>
          </dl>
          {data.text && <section className="document-reader"><div className="document-reader-heading"><FolderLock size={17} /><span>Extracted text</span></div><article>{data.text}</article></section>}
        </>
      )}
    </div>
  );
}
