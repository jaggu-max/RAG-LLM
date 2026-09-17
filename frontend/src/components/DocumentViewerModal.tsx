import { useState, useEffect } from 'react';
import {
  FileText, X, ChevronLeft, ChevronRight, ZoomIn, ZoomOut, Maximize2, Download,
  Loader2, Layers, AlignLeft, RefreshCw, AlertCircle
} from 'lucide-react';
import { API_BASE, getDocPreviewMetadata, downloadOriginalDoc } from '../services/api';

interface DocumentViewerProps {
  doc: {
    id: string;
    filename: string;
    file_type: string;
    size_bytes: number;
    chunks_count: number;
    chunks?: Array<{ chunk_id: string; text: string; page_number?: number }>;
    full_text?: string;
  };
  onClose: () => void;
  initialTab?: 'document' | 'chunks' | 'full';
  initialSlide?: number;
  highlightText?: string;
}

export default function DocumentViewerModal({
  doc,
  onClose,
  initialTab = 'document',
  initialSlide = 1,
  highlightText,
}: DocumentViewerProps) {
  const [activeTab, setActiveTab] = useState<'document' | 'chunks' | 'full'>(initialTab);
  const [currentSlide, setCurrentSlide] = useState<number>(initialSlide);
  const [zoom, setZoom] = useState<number>(100);
  const [loading, setLoading] = useState<boolean>(true);
  const [previewMeta, setPreviewMeta] = useState<{
    page_count: number;
    preview_type: string;
    has_pdf: boolean;
    has_images: boolean;
    status: string;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    setLoading(true);
    setError(null);

    getDocPreviewMetadata(doc.id)
      .then((meta) => {
        if (!isMounted) return;
        setPreviewMeta(meta);
        setLoading(false);
      })
      .catch((err) => {
        if (!isMounted) return;
        console.warn('Preview metadata fetch failed, using fallback:', err);
        setPreviewMeta({
          page_count: doc.chunks_count || 1,
          preview_type: 'fallback',
          has_pdf: doc.file_type === 'pdf',
          has_images: false,
          status: 'ready',
        });
        setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [doc.id]);

  const totalPages = previewMeta?.page_count || 1;

  const handlePrevSlide = () => {
    setCurrentSlide((prev) => Math.max(1, prev - 1));
  };

  const handleNextSlide = () => {
    setCurrentSlide((prev) => Math.min(totalPages, prev + 1));
  };

  const handleChunkClick = (pageNo?: number) => {
    if (pageNo && pageNo > 0) {
      setCurrentSlide(pageNo);
      setActiveTab('document');
    }
  };

  const formatSize = (bytes: number) => {
    if (!bytes) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  const slideImageUrl = `${API_BASE}/documents/${doc.id}/preview/slide/${currentSlide}`;
  const pdfPreviewUrl = `${API_BASE}/documents/${doc.id}/preview/pdf`;

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 slide-up">
      <div className="bg-white border-2 border-[#1E1E1E] shadow-[8px_8px_0px_#1E1E1E] w-full max-w-5xl max-h-[90vh] flex flex-col overflow-hidden">
        
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-3 bg-[#1E1E1E] text-white border-b-2 border-[#1E1E1E]">
          <div className="flex items-center gap-3">
            <FileText className="w-5 h-5 text-[#DB4A2B]" />
            <div>
              <h2 className="font-display text-base font-bold truncate max-w-[450px]">{doc.filename}</h2>
              <p className="font-mono text-[10px] text-white/70 uppercase">
                TYPE: {doc.file_type} • SIZE: {formatSize(doc.size_bytes)} • CHUNKS: {doc.chunks_count} • SLIDES: {totalPages}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => downloadOriginalDoc(doc.id, doc.filename)}
              title="Download Original File"
              className="flex items-center gap-1.5 px-3 py-1.5 bg-[#DB4A2B] text-white font-mono text-xs font-bold border border-white/20 hover:bg-[#c23b1e] transition-colors shadow-[2px_2px_0px_#000]">
              <Download className="w-3.5 h-3.5" />
              <span>DOWNLOAD ORIGINAL</span>
            </button>
            <button
              onClick={onClose}
              className="p-1 hover:bg-white/20 transition-colors rounded">
              <X className="w-5 h-5 text-white" />
            </button>
          </div>
        </div>

        {/* Modal Tabs Bar */}
        <div className="flex items-center justify-between px-6 py-2 bg-[#E4E2DD] border-b-2 border-[#1E1E1E]">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setActiveTab('document')}
              className={`font-mono text-xs font-bold px-3 py-1 border border-[#1E1E1E] transition-all flex items-center gap-1.5 ${
                activeTab === 'document' ? 'bg-[#DB4A2B] text-white shadow-[2px_2px_0px_#1E1E1E]' : 'bg-white text-[#1E1E1E]'
              }`}>
              <Layers className="w-3.5 h-3.5" />
              <span>DOCUMENT PREVIEW</span>
            </button>
            <button
              onClick={() => setActiveTab('chunks')}
              className={`font-mono text-xs font-bold px-3 py-1 border border-[#1E1E1E] transition-all flex items-center gap-1.5 ${
                activeTab === 'chunks' ? 'bg-[#DB4A2B] text-white shadow-[2px_2px_0px_#1E1E1E]' : 'bg-white text-[#1E1E1E]'
              }`}>
              <span>CHUNKS ({doc.chunks?.length || doc.chunks_count})</span>
            </button>
            <button
              onClick={() => setActiveTab('full')}
              className={`font-mono text-xs font-bold px-3 py-1 border border-[#1E1E1E] transition-all flex items-center gap-1.5 ${
                activeTab === 'full' ? 'bg-[#DB4A2B] text-white shadow-[2px_2px_0px_#1E1E1E]' : 'bg-white text-[#1E1E1E]'
              }`}>
              <AlignLeft className="w-3.5 h-3.5" />
              <span>EXTRACTED TEXT</span>
            </button>
          </div>

          {/* Slide Navigation Controls */}
          {activeTab === 'document' && totalPages > 1 && (
            <div className="flex items-center gap-3 font-mono text-xs">
              <div className="flex items-center gap-1 bg-white border border-[#1E1E1E] px-2 py-0.5 shadow-[2px_2px_0px_#1E1E1E]">
                <button
                  onClick={handlePrevSlide}
                  disabled={currentSlide <= 1}
                  className="p-1 hover:bg-[#F0EEE6] disabled:opacity-30 disabled:hover:bg-transparent">
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <span className="font-bold px-2">
                  Slide {currentSlide} / {totalPages}
                </span>
                <button
                  onClick={handleNextSlide}
                  disabled={currentSlide >= totalPages}
                  className="p-1 hover:bg-[#F0EEE6] disabled:opacity-30 disabled:hover:bg-transparent">
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>

              {/* Zoom Controls */}
              <div className="flex items-center gap-1 bg-white border border-[#1E1E1E] px-2 py-0.5 shadow-[2px_2px_0px_#1E1E1E]">
                <button
                  onClick={() => setZoom((z) => Math.max(50, z - 25))}
                  className="p-1 hover:bg-[#F0EEE6]">
                  <ZoomOut className="w-3.5 h-3.5" />
                </button>
                <span className="font-bold text-[11px] w-9 text-center">{zoom}%</span>
                <button
                  onClick={() => setZoom((z) => Math.min(200, z + 25))}
                  className="p-1 hover:bg-[#F0EEE6]">
                  <ZoomIn className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={() => setZoom(100)}
                  title="Reset Zoom"
                  className="p-1 hover:bg-[#F0EEE6] text-[10px] font-bold border-l border-[#1E1E1E] ml-1 pl-1.5">
                  100%
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto p-4 font-mono text-xs bg-[#F4F2ED]">
          {/* Passage Highlight Banner */}
          {highlightText && (
            <div className="mb-3 p-3 bg-yellow-100 border-2 border-[#1E1E1E] shadow-[3px_3px_0px_#1E1E1E]">
              <div className="flex items-center gap-2 mb-1">
                <AlertCircle className="w-4 h-4 text-[#DB4A2B]" />
                <span className="font-mono text-xs font-bold uppercase text-[#1E1E1E]">MATCHING EVIDENCE PASSAGE:</span>
              </div>
              <p className="font-mono text-xs text-[#1E1E1E] bg-yellow-300/80 px-2 py-1 border border-[#1E1E1E] font-medium leading-relaxed">
                "{highlightText}"
              </p>
            </div>
          )}

          {activeTab === 'document' && (
            <div className="w-full h-[65vh] border-2 border-[#1E1E1E] bg-[#EAE8E3] overflow-auto shadow-[4px_4px_0px_#1E1E1E] flex flex-col items-center justify-center relative p-4">
              {loading ? (
                <div className="flex flex-col items-center gap-3 text-[#1E1E1E]">
                  <Loader2 className="w-8 h-8 animate-spin text-[#DB4A2B]" />
                  <p className="font-bold">Preparing presentation slides preview...</p>
                </div>
              ) : previewMeta?.has_images ? (
                <div
                  className="transition-all duration-200 shadow-xl border-2 border-[#1E1E1E] bg-white max-h-full flex items-center justify-center overflow-hidden"
                  style={{ transform: `scale(${zoom / 100})`, transformOrigin: 'center center' }}>
                  <img
                    src={slideImageUrl}
                    alt={`Slide ${currentSlide}`}
                    className="max-h-[58vh] max-w-full object-contain"
                    onError={(e) => {
                      // Fallback to PDF iframe if image fails
                      (e.target as HTMLElement).style.display = 'none';
                    }}
                  />
                </div>
              ) : previewMeta?.has_pdf ? (
                <iframe
                  src={pdfPreviewUrl}
                  title="PDF Preview"
                  className="w-full h-full border-0"
                />
              ) : (
                /* Fallback text preview */
                <div className="w-full h-full bg-white p-6 overflow-auto border border-[#1E1E1E]">
                  <h3 className="font-bold text-sm mb-4 pb-2 border-b border-[#1E1E1E] text-[#DB4A2B]">
                    EXTRACTED SLIDE CONTENT (SLIDE {currentSlide} / {totalPages})
                  </h3>
                  <pre className="font-mono text-xs whitespace-pre-wrap leading-relaxed text-[#1E1E1E]">
                    {doc.full_text || 'No preview available.'}
                  </pre>
                </div>
              )}
            </div>
          )}

          {activeTab === 'chunks' && (
            <div className="space-y-3 max-h-[65vh] overflow-y-auto pr-2">
              {doc.chunks && doc.chunks.length > 0 ? (
                doc.chunks.map((c, i) => (
                  <div
                    key={c.chunk_id || i}
                    onClick={() => handleChunkClick(c.page_number || (i + 1))}
                    className="p-3 bg-white border-2 border-[#1E1E1E] shadow-[3px_3px_0px_#1E1E1E] hover:border-[#DB4A2B] hover:shadow-[3px_3px_0px_#DB4A2B] cursor-pointer transition-all">
                    <div className="flex items-center justify-between border-b border-[#1E1E1E]/20 pb-1.5 mb-2">
                      <span className="font-bold text-[#DB4A2B]">CHUNK #{i + 1}</span>
                      <div className="flex items-center gap-2 font-mono text-[10px] text-[#1E1E1E]/70">
                        {c.page_number && <span className="bg-[#E4E2DD] px-1.5 py-0.5 border border-[#1E1E1E]">SLIDE {c.page_number}</span>}
                        <span>ID: {c.chunk_id}</span>
                      </div>
                    </div>
                    <p className="text-xs leading-relaxed whitespace-pre-wrap font-mono">{c.text}</p>
                  </div>
                ))
              ) : (
                <div className="p-8 text-center bg-white border-2 border-[#1E1E1E]">
                  <p>No chunk data extracted.</p>
                </div>
              )}
            </div>
          )}

          {activeTab === 'full' && (
            <div className="w-full h-[65vh] bg-white border-2 border-[#1E1E1E] p-6 overflow-auto shadow-[4px_4px_0px_#1E1E1E]">
              <pre className="font-mono text-xs whitespace-pre-wrap leading-relaxed text-[#1E1E1E]">
                {doc.full_text || 'No text extracted.'}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
