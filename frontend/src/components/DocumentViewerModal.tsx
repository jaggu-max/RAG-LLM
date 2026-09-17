import { useState, useEffect, useRef } from 'react';
import {
  FileText, X, ChevronLeft, ChevronRight, ZoomIn, ZoomOut, Download,
  Loader2, Layers, AlignLeft, AlertCircle, Eye, FileCode
} from 'lucide-react';
import { API_BASE, downloadOriginalDoc } from '../services/api';

interface LayoutBlock {
  block_id: string;
  text: string;
  type: string;
  page?: number;
  bbox?: [number, number, number, number]; // [x, y, w, h]
  line_number?: number;
  confidence?: number;
}

interface DocumentViewerProps {
  doc: {
    id: string;
    filename: string;
    file_type: string;
    size_bytes: number;
    chunks_count: number;
    chunks?: Array<{ chunk_id: string; text: string; page_number?: number }>;
    full_text?: string;
    status?: string;
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
  const [ocrViewMode, setOcrViewMode] = useState<'structured' | 'raw'>('structured');
  const [currentSlide, setCurrentSlide] = useState<number>(initialSlide);
  const [zoom, setZoom] = useState<number>(100);
  const [loading, setLoading] = useState<boolean>(true);
  const [showEvidenceBanner, setShowEvidenceBanner] = useState<boolean>(true);
  const [isEvidenceExpanded, setIsEvidenceExpanded] = useState<boolean>(false);
  const [docContent, setDocContent] = useState<{
    full_text: string;
    raw_ocr: string;
    structured_ocr: string;
    layout_blocks: LayoutBlock[];
    chunks: Array<{ chunk_id: string; text: string; page_number?: number }>;
  } | null>(null);

  const [hoveredBlockId, setHoveredBlockId] = useState<string | null>(null);
  const [selectedBlockId, setSelectedBlockId] = useState<string | null>(null);

  const imgRef = useRef<HTMLImageElement>(null);
  const [imgDims, setImgDims] = useState<{ naturalWidth: number; naturalHeight: number; clientWidth: number; clientHeight: number } | null>(null);

  useEffect(() => {
    let isMounted = true;
    setLoading(true);

    fetch(`${API_BASE}/documents/${doc.id}/content`)
      .then((res) => res.json())
      .then((data) => {
        if (!isMounted) return;
        setDocContent(data);
        setLoading(false);
      })
      .catch((err) => {
        if (!isMounted) return;
        console.warn('Document content fetch error:', err);
        setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [doc.id]);

  const handleImageLoad = () => {
    if (imgRef.current) {
      setImgDims({
        naturalWidth: imgRef.current.naturalWidth || 1,
        naturalHeight: imgRef.current.naturalHeight || 1,
        clientWidth: imgRef.current.clientWidth || 1,
        clientHeight: imgRef.current.clientHeight || 1,
      });
    }
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

  const isImageFile = ['png', 'jpg', 'jpeg', 'webp', 'image'].includes((doc.file_type || '').toLowerCase());
  const rawImageUrl = `${API_BASE}/documents/${doc.id}/file`;
  const pdfPreviewUrl = `${API_BASE}/documents/${doc.id}/preview/pdf`;

  const blocks = docContent?.layout_blocks || [];
  const rawOcrText = docContent?.raw_ocr || docContent?.full_text || doc.full_text || '';
  const structuredOcrText = docContent?.structured_ocr || docContent?.full_text || doc.full_text || '';

  return (
    <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-3 slide-up">
      <div className="bg-white border-2 border-[#1E1E1E] shadow-[8px_8px_0px_#1E1E1E] w-full max-w-6xl max-h-[94vh] flex flex-col overflow-hidden">
        
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-3 bg-[#1E1E1E] text-white border-b-2 border-[#1E1E1E]">
          <div className="flex items-center gap-3">
            <FileText className="w-5 h-5 text-[#DB4A2B]" />
            <div>
              <h2 className="font-display text-base font-bold truncate max-w-[500px]">{doc.filename}</h2>
              <p className="font-mono text-[10px] text-white/70 uppercase">
                TYPE: {doc.file_type} • SIZE: {formatSize(doc.size_bytes)} • CHUNKS: {doc.chunks_count} • DETECTED BLOCKS: {blocks.length}
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

        {/* Modal Navigation & Controls Bar */}
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
              <span>CHUNKS ({docContent?.chunks?.length || doc.chunks_count})</span>
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

          {/* View Mode & Zoom Controls */}
          {activeTab === 'document' && (
            <div className="flex items-center gap-3 font-mono text-xs">
              <div className="flex items-center bg-white border border-[#1E1E1E] shadow-[2px_2px_0px_#1E1E1E]">
                <button
                  onClick={() => setOcrViewMode('structured')}
                  className={`px-2.5 py-1 text-[11px] font-bold ${
                    ocrViewMode === 'structured' ? 'bg-[#1E1E1E] text-white' : 'text-[#1E1E1E] hover:bg-gray-100'
                  }`}>
                  Structured Document
                </button>
                <button
                  onClick={() => setOcrViewMode('raw')}
                  className={`px-2.5 py-1 text-[11px] font-bold border-l border-[#1E1E1E] ${
                    ocrViewMode === 'raw' ? 'bg-[#1E1E1E] text-white' : 'text-[#1E1E1E] hover:bg-gray-100'
                  }`}>
                  Raw Faithful OCR
                </button>
              </div>

              <div className="flex items-center gap-1 bg-white border border-[#1E1E1E] px-2 py-0.5 shadow-[2px_2px_0px_#1E1E1E]">
                <button onClick={() => setZoom((z) => Math.max(50, z - 25))} className="p-1 hover:bg-[#F0EEE6]">
                  <ZoomOut className="w-3.5 h-3.5" />
                </button>
                <span className="font-bold text-[11px] w-9 text-center">{zoom}%</span>
                <button onClick={() => setZoom((z) => Math.min(200, z + 25))} className="p-1 hover:bg-[#F0EEE6]">
                  <ZoomIn className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto p-4 font-mono text-xs bg-[#F4F2ED]">
          {/* Highlight Banner — Compact & Dismissible */}
          {highlightText && showEvidenceBanner && (
            <div className="mb-2 p-2 bg-yellow-100 border-2 border-[#1E1E1E] shadow-[2px_2px_0px_#1E1E1E] flex items-start justify-between gap-2">
              <div className="flex items-start gap-2 flex-1 min-w-0">
                <AlertCircle className="w-4 h-4 text-[#DB4A2B] shrink-0 mt-0.5" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[11px] font-bold uppercase text-[#1E1E1E]">MATCHING EVIDENCE PASSAGE:</span>
                    <button
                      onClick={() => setIsEvidenceExpanded(!isEvidenceExpanded)}
                      className="font-mono text-[10px] text-[#DB4A2B] underline font-bold hover:text-black">
                      {isEvidenceExpanded ? '[COLLAPSE]' : '[EXPAND FULL TEXT]'}
                    </button>
                  </div>
                  <p className={`font-mono text-[11px] text-[#1E1E1E] bg-yellow-200/80 px-2 py-1 border border-[#1E1E1E]/40 font-medium leading-normal mt-1 ${
                    isEvidenceExpanded ? 'whitespace-pre-wrap' : 'truncate'
                  }`}>
                    "{highlightText}"
                  </p>
                </div>
              </div>
              <button
                onClick={() => setShowEvidenceBanner(false)}
                title="Dismiss evidence banner"
                className="p-1 hover:bg-yellow-300 text-[#1E1E1E] border border-[#1E1E1E] bg-white rounded shrink-0">
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          )}

          {activeTab === 'document' && (
            <div className="w-full h-[70vh] border-2 border-[#1E1E1E] bg-[#EAE8E3] overflow-auto shadow-[4px_4px_0px_#1E1E1E] flex flex-col items-center justify-center relative p-4">
              {loading ? (
                <div className="flex flex-col items-center gap-3 text-[#1E1E1E]">
                  <Loader2 className="w-8 h-8 animate-spin text-[#DB4A2B]" />
                  <p className="font-bold">Loading document view...</p>
                </div>
              ) : isImageFile ? (
                <div
                  className="transition-all duration-200 shadow-xl border-2 border-[#1E1E1E] bg-white max-h-full flex items-center justify-center overflow-hidden"
                  style={{ transform: `scale(${zoom / 100})`, transformOrigin: 'center center' }}>
                  <img
                    src={rawImageUrl}
                    alt={doc.filename}
                    className="max-h-[66vh] max-w-full object-contain"
                  />
                </div>
              ) : (
                <iframe src={pdfPreviewUrl} title="PDF Preview" className="w-full h-full border-0" />
              )}
            </div>
          )}

          {activeTab === 'chunks' && (
            <div className="space-y-3 max-h-[70vh] overflow-y-auto pr-2">
              {docContent?.chunks && docContent.chunks.length > 0 ? (
                docContent.chunks.map((c, i) => (
                  <div
                    key={c.chunk_id || i}
                    onClick={() => handleChunkClick(c.page_number || (i + 1))}
                    className="p-4 bg-white border-2 border-[#1E1E1E] shadow-[3px_3px_0px_#1E1E1E] hover:border-[#DB4A2B] hover:shadow-[3px_3px_0px_#DB4A2B] cursor-pointer transition-all">
                    <div className="flex items-center justify-between border-b border-[#1E1E1E]/20 pb-2 mb-3">
                      <span className="font-bold text-[#DB4A2B] font-mono">DOCUMENT CHUNK #{i + 1}</span>
                      <div className="flex items-center gap-2 font-mono text-[10px] text-[#1E1E1E]/70">
                        {c.page_number && <span className="bg-[#E4E2DD] px-2 py-0.5 border border-[#1E1E1E] font-bold">PAGE {c.page_number}</span>}
                        <span>ID: {c.chunk_id}</span>
                      </div>
                    </div>
                    <p className="text-xs leading-relaxed whitespace-pre-wrap font-mono text-[#1E1E1E]">{c.text}</p>
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
            <div className="w-full h-[70vh] bg-white border-2 border-[#1E1E1E] p-6 overflow-auto shadow-[4px_4px_0px_#1E1E1E] flex flex-col">
              {(!rawOcrText || rawOcrText.includes("OCR processing complete") || doc.status === 'failed') && (
                <div className="mb-4 p-4 bg-[#FFF5F2] border-2 border-[#DB4A2B] shadow-[3px_3px_0px_#DB4A2B] flex flex-col md:flex-row items-center justify-between gap-3">
                  <div className="flex items-center gap-2 text-[#DB4A2B]">
                    <AlertCircle className="w-5 h-5 shrink-0" />
                    <div>
                      <p className="font-bold text-xs uppercase">OCR Processing Status</p>
                      <p className="text-[11px] font-sans">
                        {doc.status === 'failed' ? 'OCR failed — Reprocess required' : 'Placeholder text detected. Trigger reprocessing to extract full text.'}
                      </p>
                    </div>
                  </div>
                  <button
                    onClick={async () => {
                      try {
                        setLoading(true);
                        await fetch(`${API_BASE}/documents/${doc.id}/reprocess_ocr`, { method: 'POST' });
                        window.location.reload();
                      } catch (err) {
                        alert('Reprocessing failed: ' + err);
                      } finally {
                        setLoading(false);
                      }
                    }}
                    className="px-3 py-1.5 bg-[#DB4A2B] text-white font-bold text-xs border border-[#1E1E1E] shadow-[2px_2px_0px_#1E1E1E] hover:translate-x-0.5 hover:translate-y-0.5 transition-all shrink-0">
                    🔄 REPROCESS OCR
                  </button>
                </div>
              )}
              <pre className="font-mono text-xs whitespace-pre-wrap leading-relaxed text-[#1E1E1E] flex-1">
                {structuredOcrText || rawOcrText || 'No text extracted.'}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
