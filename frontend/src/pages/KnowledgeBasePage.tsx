import { useState, useEffect, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { Upload, FileText, Trash2, RefreshCw, Database, CheckCircle2, AlertCircle, Loader2, Eye, X } from 'lucide-react';
import { getDocuments, uploadDocument, deleteDocument, reindexDocument, reindexAll, getDocumentContent } from '../services/api';
import type { DocumentItem } from '../types';

interface DocumentPreviewData {
  id: string;
  filename: string;
  file_type: string;
  size_bytes: number;
  chunks_count: number;
  status: string;
  full_text: string;
  chunks: Array<{ chunk_id: string; text: string }>;
}

export default function KnowledgeBasePage() {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [reindexingId, setReindexingId] = useState<string | null>(null);
  const [reindexingAll, setReindexingAllState] = useState(false);
  const [previewDoc, setPreviewDoc] = useState<DocumentPreviewData | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<'document' | 'chunks' | 'full'>('document');

  const [uploadState, setUploadState] = useState<{
    filename: string;
    percent: number;
    status: 'uploading' | 'indexing' | 'success' | 'error';
    errorMsg?: string;
  } | null>(null);

  const fetchDocs = async () => {
    try {
      const res = await getDocuments();
      setDocuments(res.documents);
    } catch (e) {
      console.error('Failed to fetch documents:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchDocs(); }, []);

  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    setUploading(true);
    for (const file of acceptedFiles) {
      setUploadState({ filename: file.name, percent: 0, status: 'uploading' });
      try {
        await uploadDocument(file, (percent) => {
          setUploadState({
            filename: file.name,
            percent: percent === 100 ? 99 : percent,
            status: percent === 100 ? 'indexing' : 'uploading',
          });
        });
        setUploadState({ filename: file.name, percent: 100, status: 'success' });
        setTimeout(() => {
          setUploadState(null);
        }, 4000);
      } catch (e: any) {
        console.error('Upload failed:', e);
        const msg = e.response?.data?.detail || e.message;
        setUploadState({ filename: file.name, percent: 0, status: 'error', errorMsg: msg });
        setTimeout(() => {
          setUploadState(null);
        }, 6000);
      }
    }
    setUploading(false);
    fetchDocs();
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf'],
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
      'text/plain': ['.txt'],
      'text/markdown': ['.md'],
      'text/csv': ['.csv'],
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
      'application/vnd.openxmlformats-officedocument.presentationml.presentation': ['.pptx'],
      'application/json': ['.json'],
      'image/png': ['.png'],
      'image/jpeg': ['.jpg', '.jpeg'],
    },
  });

  const [deletingId, setDeletingId] = useState<string | null>(null);

  const handleDelete = async (id: string) => {
    setDeletingId(id);
    setDocuments(prev => prev.filter(d => d.id !== id));
    try {
      await deleteDocument(id);
    } catch (e) {
      console.error('Failed to delete document:', e);
    } finally {
      setDeletingId(null);
      await fetchDocs();
    }
  };

  const handleReindex = async (id: string) => {
    setReindexingId(id);
    try {
      await reindexDocument(id);
      await fetchDocs();
    } catch (e) {
      console.error('Failed to reindex document:', e);
    } finally {
      setReindexingId(null);
    }
  };

  const handleReindexAll = async () => {
    setReindexingAllState(true);
    try {
      await reindexAll();
      await fetchDocs();
    } catch (e) {
      console.error('Failed to reindex all:', e);
    } finally {
      setReindexingAllState(false);
    }
  };

  const handleView = async (id: string) => {
    setPreviewLoading(true);
    try {
      const data = await getDocumentContent(id);
      setPreviewDoc(data);
    } catch (e) {
      console.error('Failed to load document content:', e);
      alert('Failed to load document content.');
    } finally {
      setPreviewLoading(false);
    }
  };

  const totalChunks = documents.reduce((s, d) => s + d.chunks, 0);
  const indexed = documents.filter(d => d.status === 'indexed').length;
  const processing = documents.filter(d => d.status === 'processing' || d.status === 'pending').length;
  const failed = documents.filter(d => d.status === 'failed').length;

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
  };

  return (
    <div className="flex-1 overflow-y-auto px-6 py-6 bg-[#E4E2DD] text-[#1E1E1E] slide-up">
      <div className="max-w-5xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6 pb-4 border-b-2 border-[#1E1E1E]">
          <div>
            <span className="font-mono text-xs font-bold uppercase tracking-widest text-white bg-[#1E1E1E] px-2 py-0.5 border border-[#1E1E1E]">REPOSITORY</span>
            <h1 className="font-display text-2xl font-bold tracking-tight text-[#1E1E1E] mt-1">Knowledge Base</h1>
            <p className="font-sans text-xs font-medium text-[#1E1E1E]/70">Manage dataset documents and indexed vector embeddings</p>
          </div>
          <button onClick={handleReindexAll}
                  disabled={reindexingAll}
                  className="btn-secondary text-xs uppercase tracking-wider flex items-center gap-2 disabled:opacity-50">
            <RefreshCw className={`w-3.5 h-3.5 ${reindexingAll ? 'animate-spin' : ''}`} />
            {reindexingAll ? 'Reindexing All...' : 'Reindex All'}
          </button>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
          {[
            { label: 'Total', value: documents.length, icon: Database, bg: 'bg-[#DB4A2B] text-white' },
            { label: 'Indexed', value: indexed, icon: CheckCircle2, bg: 'bg-white text-[#1E1E1E]' },
            { label: 'Processing', value: processing, icon: Loader2, bg: 'bg-[#F8A348] text-[#1E1E1E]' },
            { label: 'Failed', value: failed, icon: AlertCircle, bg: 'bg-[#FF89A9] text-[#1E1E1E]' },
            { label: 'Chunks', value: totalChunks, icon: FileText, bg: 'bg-[#1E1E1E] text-[#E4E2DD]' },
          ].map(({ label, value, icon: Icon, bg }) => (
            <div key={label} className={`${bg} border-2 border-[#1E1E1E] shadow-[4px_4px_0px_#1E1E1E] p-4`}>
              <div className="flex items-center gap-2 mb-1">
                <Icon className="w-4 h-4 flex-shrink-0" />
                <span className="font-mono text-[10px] font-bold uppercase tracking-wider">{label}</span>
              </div>
              <p className="font-display text-2xl font-bold leading-none">{value}</p>
            </div>
          ))}
        </div>

        {/* Upload Zone */}
        <div {...getRootProps()}
             className={`bg-white border-2 border-dashed border-[#1E1E1E] shadow-[4px_4px_0px_#1E1E1E]
               p-8 text-center cursor-pointer transition-all duration-200 mb-6 hover:shadow-[6px_6px_0px_#DB4A2B]
               ${isDragActive ? 'bg-[#DB4A2B]/10 border-solid border-[#DB4A2B]' : ''}`}>
          <input {...getInputProps()} />
          <Upload className={`w-10 h-10 mx-auto mb-3 ${isDragActive ? 'text-[#DB4A2B]' : 'text-[#1E1E1E]'}`} />
          {uploading ? (
            <p className="font-bold text-sm text-[#DB4A2B] uppercase">Processing upload...</p>
          ) : isDragActive ? (
            <p className="font-bold text-sm text-[#DB4A2B] uppercase">Drop files here</p>
          ) : (
            <>
              <p className="font-display text-base font-bold text-[#1E1E1E] mb-1 uppercase tracking-tight">Drag & Drop files here</p>
              <p className="font-mono text-xs text-[#1E1E1E]/70">or click to browse • PDF, DOCX, CSV, XLSX, TXT, MD, PPTX, JSON, Images</p>
            </>
          )}
        </div>

        {/* Upload Progress Indicator */}
        {uploadState && (
          <div className="bg-white border-2 border-[#1E1E1E] shadow-[4px_4px_0px_#1E1E1E] p-4 mb-6 transition-all duration-300">
            <div className="flex items-center justify-between font-mono text-xs font-bold mb-2">
              <span className="truncate max-w-[300px] text-[#1E1E1E]">{uploadState.filename}</span>
              <span className={`uppercase ${uploadState.status === 'error' ? 'text-red-600' : 'text-[#DB4A2B]'}`}>
                {uploadState.status === 'uploading' && `Uploading... ${uploadState.percent}%`}
                {uploadState.status === 'indexing' && `Indexing Document... 99%`}
                {uploadState.status === 'success' && `100% — Successfully Uploaded!`}
                {uploadState.status === 'error' && `Upload Failed: ${uploadState.errorMsg || 'Error'}`}
              </span>
            </div>
            <div className="w-full bg-[#E4E2DD] border border-[#1E1E1E] h-4 overflow-hidden relative">
              <div
                className={`h-full transition-all duration-300 ease-out ${uploadState.status === 'error' ? 'bg-red-600' : 'bg-[#DB4A2B]'}`}
                style={{ width: `${uploadState.percent}%` }}
              />
            </div>
          </div>
        )}

        {/* Document Table */}
        {loading ? (
          <div className="text-center py-12 font-mono text-sm font-bold text-[#1E1E1E]/60 uppercase">Loading documents...</div>
        ) : documents.length === 0 ? (
          <div className="bg-white border-2 border-[#1E1E1E] shadow-[4px_4px_0px_#1E1E1E] text-center py-12 p-6">
            <Database className="w-12 h-12 mx-auto mb-3 text-[#DB4A2B]" />
            <p className="font-display text-lg font-bold uppercase text-[#1E1E1E]">No documents in knowledge base</p>
            <p className="font-sans text-xs font-medium text-[#1E1E1E]/70 mt-1">Upload files above or drop them into <code className="bg-[#E4E2DD] px-1 font-mono">backend/dataset/</code></p>
          </div>
        ) : (
          <div className="bg-white border-2 border-[#1E1E1E] shadow-[6px_6px_0px_#1E1E1E] overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="bg-[#1E1E1E] text-[#E4E2DD] font-mono text-xs uppercase tracking-wider">
                    <th className="px-4 py-3 border-r border-white/20 font-bold">File</th>
                    <th className="px-4 py-3 border-r border-white/20 font-bold">Type</th>
                    <th className="px-4 py-3 border-r border-white/20 font-bold hidden sm:table-cell">Size</th>
                    <th className="px-4 py-3 border-r border-white/20 font-bold hidden md:table-cell">Chunks</th>
                    <th className="px-4 py-3 border-r border-white/20 font-bold">Status</th>
                    <th className="px-4 py-3 border-r border-white/20 font-bold hidden lg:table-cell">Updated</th>
                    <th className="px-4 py-3 font-bold text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y-2 divide-[#1E1E1E] font-sans text-xs">
                  {documents.map(doc => (
                    <tr key={doc.id} className="hover:bg-[#E4E2DD]/50 transition-colors">
                      <td className="px-4 py-3 border-r-2 border-[#1E1E1E]">
                        <div className="flex items-center gap-2">
                          <FileText className="w-4 h-4 flex-shrink-0 text-[#DB4A2B]" />
                          <span className="font-bold text-[#1E1E1E] truncate max-w-[200px]">{doc.filename}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3 border-r-2 border-[#1E1E1E] font-mono uppercase font-bold text-[10px]">
                        {doc.file_type}
                      </td>
                      <td className="px-4 py-3 border-r-2 border-[#1E1E1E] hidden sm:table-cell font-mono text-xs">{formatSize(doc.size_bytes)}</td>
                      <td className="px-4 py-3 border-r-2 border-[#1E1E1E] hidden md:table-cell font-bold">{doc.chunks}</td>
                      <td className="px-4 py-3 border-r-2 border-[#1E1E1E]">
                        <StatusBadge status={doc.status} />
                      </td>
                      <td className="px-4 py-3 border-r-2 border-[#1E1E1E] hidden lg:table-cell font-mono text-[10px]">
                        {doc.updated_at ? new Date(doc.updated_at).toLocaleDateString() : '—'}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <div className="flex items-center justify-end gap-1">
                          {/* Eye / View Button */}
                          <button onClick={() => handleView(doc.id)}
                                  disabled={previewLoading}
                                  className="p-1.5 border border-[#1E1E1E] bg-[#E4E2DD] hover:bg-[#1E1E1E] hover:text-white transition-colors" title="View document content" aria-label="View document content">
                            <Eye className="w-3.5 h-3.5" />
                          </button>
                          {/* Refresh / Reindex Button */}
                          <button onClick={() => handleReindex(doc.id)}
                                  disabled={reindexingId === doc.id}
                                  className="p-1.5 border border-[#1E1E1E] bg-[#E4E2DD] hover:bg-[#DB4A2B] hover:text-white transition-colors" title="Reindex document" aria-label="Reindex document">
                            <RefreshCw className={`w-3.5 h-3.5 ${reindexingId === doc.id ? 'animate-spin text-[#DB4A2B]' : ''}`} />
                          </button>
                          {/* Delete Button */}
                          <button onClick={() => handleDelete(doc.id)}
                                  disabled={deletingId === doc.id}
                                  className="p-1.5 border border-[#1E1E1E] bg-[#E4E2DD] hover:bg-red-600 hover:text-white transition-colors disabled:opacity-50" title="Delete document" aria-label="Delete document">
                            {deletingId === doc.id ? (
                              <Loader2 className="w-3.5 h-3.5 animate-spin text-red-600" />
                            ) : (
                              <Trash2 className="w-3.5 h-3.5" />
                            )}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {/* Document Preview Modal */}
      {previewDoc && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white border-2 border-[#1E1E1E] shadow-[8px_8px_0px_#1E1E1E] w-full max-w-4xl max-h-[85vh] flex flex-col slide-up">
            {/* Modal Header */}
            <div className="flex items-center justify-between px-6 py-4 bg-[#1E1E1E] text-white border-b-2 border-[#1E1E1E]">
              <div className="flex items-center gap-3">
                <FileText className="w-5 h-5 text-[#DB4A2B]" />
                <div>
                  <h2 className="font-display text-base font-bold truncate max-w-[400px]">{previewDoc.filename}</h2>
                  <p className="font-mono text-[10px] text-white/70 uppercase">
                    TYPE: {previewDoc.file_type} • SIZE: {formatSize(previewDoc.size_bytes)} • CHUNKS: {previewDoc.chunks_count}
                  </p>
                </div>
              </div>
              <button onClick={() => setPreviewDoc(null)} className="p-1 hover:bg-white/20 transition-colors">
                <X className="w-5 h-5 text-white" />
              </button>
            </div>

            {/* Modal Tabs */}
            <div className="flex items-center gap-2 px-6 py-2 bg-[#E4E2DD] border-b-2 border-[#1E1E1E]">
              <button
                onClick={() => setActiveTab('document')}
                className={`font-mono text-xs font-bold px-3 py-1 border border-[#1E1E1E] transition-all ${
                  activeTab === 'document' ? 'bg-[#DB4A2B] text-white shadow-[2px_2px_0px_#1E1E1E]' : 'bg-white text-[#1E1E1E]'
                }`}>
                DOCUMENT PREVIEW
              </button>
              <button
                onClick={() => setActiveTab('chunks')}
                className={`font-mono text-xs font-bold px-3 py-1 border border-[#1E1E1E] transition-all ${
                  activeTab === 'chunks' ? 'bg-[#DB4A2B] text-white shadow-[2px_2px_0px_#1E1E1E]' : 'bg-white text-[#1E1E1E]'
                }`}>
                CHUNKS ({previewDoc.chunks.length})
              </button>
              <button
                onClick={() => setActiveTab('full')}
                className={`font-mono text-xs font-bold px-3 py-1 border border-[#1E1E1E] transition-all ${
                  activeTab === 'full' ? 'bg-[#DB4A2B] text-white shadow-[2px_2px_0px_#1E1E1E]' : 'bg-white text-[#1E1E1E]'
                }`}>
                EXTRACTED TEXT
              </button>
            </div>

            {/* Modal Content Body */}
            <div className="flex-1 overflow-y-auto p-4 font-mono text-xs text-[#1E1E1E]">
              {activeTab === 'document' ? (
                <div className="w-full h-[60vh] border-2 border-[#1E1E1E] bg-white overflow-hidden shadow-[4px_4px_0px_#1E1E1E] flex flex-col">
                  <object
                    data={`http://localhost:8000/api/documents/${previewDoc.id}/file`}
                    type={previewDoc.file_type === 'pdf' ? 'application/pdf' : 'text/plain'}
                    className="w-full h-full"
                  >
                    <embed
                      src={`http://localhost:8000/api/documents/${previewDoc.id}/file`}
                      type={previewDoc.file_type === 'pdf' ? 'application/pdf' : 'text/plain'}
                      className="w-full h-full"
                    />
                    <div className="p-8 text-center">
                      <p className="font-bold text-sm mb-2">Unable to embed viewer directly in your browser.</p>
                      <a
                        href={`http://localhost:8000/api/documents/${previewDoc.id}/file`}
                        target="_blank"
                        rel="noreferrer"
                        className="btn-primary text-xs uppercase inline-block px-4 py-2"
                      >
                        Open Document in New Tab
                      </a>
                    </div>
                  </object>
                </div>
              ) : activeTab === 'chunks' ? (
                <div className="space-y-4">
                  {previewDoc.chunks.length === 0 ? (
                    <p className="text-center text-gray-500 py-8">No text chunks extracted yet.</p>
                  ) : (
                    previewDoc.chunks.map((c, idx) => (
                      <div key={c.chunk_id || idx} className="bg-[#E4E2DD]/40 border-2 border-[#1E1E1E] p-4 shadow-[3px_3px_0px_#1E1E1E]">
                        <div className="flex items-center justify-between mb-2 pb-1 border-b border-[#1E1E1E]/20">
                          <span className="font-mono text-[10px] font-bold uppercase text-[#DB4A2B]">CHUNK #{idx + 1}</span>
                          <span className="font-mono text-[10px] text-gray-500">{c.chunk_id}</span>
                        </div>
                        <pre className="whitespace-pre-wrap font-sans text-xs text-[#1E1E1E] leading-relaxed">{c.text}</pre>
                      </div>
                    ))
                  )}
                </div>
              ) : (
                <div className="bg-[#E4E2DD]/40 border-2 border-[#1E1E1E] p-4 shadow-[3px_3px_0px_#1E1E1E]">
                  <pre className="whitespace-pre-wrap font-sans text-xs text-[#1E1E1E] leading-relaxed">{previewDoc.full_text}</pre>
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="px-6 py-3 bg-[#E4E2DD] border-t-2 border-[#1E1E1E] flex items-center justify-between">
              <span className="font-mono text-[10px] uppercase font-bold text-[#1E1E1E]/70">STATUS: {previewDoc.status}</span>
              <button onClick={() => setPreviewDoc(null)} className="btn-secondary text-xs uppercase font-bold px-4 py-1.5">
                Close Viewer
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    indexed: 'bg-[#DB4A2B] text-white',
    processing: 'bg-[#F8A348] text-[#1E1E1E]',
    pending: 'bg-[#F8A348] text-[#1E1E1E]',
    failed: 'bg-[#FF89A9] text-[#1E1E1E]',
  };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 border border-[#1E1E1E] font-mono text-[10px] font-bold uppercase ${styles[status] || styles.pending}`}>
      {status}
    </span>
  );
}
