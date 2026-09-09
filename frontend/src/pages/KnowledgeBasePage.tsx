import { useState, useEffect, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { Upload, FileText, Trash2, RefreshCw, Database, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react';
import { getDocuments, uploadDocument, deleteDocument, reindexDocument, reindexAll } from '../services/api';
import type { DocumentItem } from '../types';

export default function KnowledgeBasePage() {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
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

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this document? This will remove all indexed data.')) return;
    setDocuments(prev => prev.filter(d => d.id !== id));
    try {
      await deleteDocument(id);
      fetchDocs();
    } catch (e) {
      console.error('Failed to delete document:', e);
      fetchDocs();
    }
  };

  const handleReindex = async (id: string) => {
    try {
      await reindexDocument(id);
      fetchDocs();
    } catch (e) { console.error(e); }
  };

  const handleReindexAll = async () => {
    try {
      await reindexAll();
      fetchDocs();
    } catch (e) { console.error(e); }
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
                  className="btn-secondary text-xs uppercase tracking-wider flex items-center gap-2">
            <RefreshCw className="w-3.5 h-3.5" />
            Reindex All
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
                          <button onClick={() => handleReindex(doc.id)}
                                  className="p-1.5 border border-[#1E1E1E] bg-[#E4E2DD] hover:bg-[#DB4A2B] hover:text-white transition-colors" title="Reindex" aria-label="Reindex document">
                            <RefreshCw className="w-3.5 h-3.5" />
                          </button>
                          <button onClick={() => handleDelete(doc.id)}
                                  className="p-1.5 border border-[#1E1E1E] bg-[#E4E2DD] hover:bg-red-600 hover:text-white transition-colors" title="Delete" aria-label="Delete document">
                            <Trash2 className="w-3.5 h-3.5" />
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
