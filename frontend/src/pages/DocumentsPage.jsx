import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Document, Page } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import { apiClient } from "../api/client.js";
import "./DocumentsPage.css";

function normalizeList(data) {
  if (Array.isArray(data)) return data;
  if (data && Array.isArray(data.results)) return data.results;
  return [];
}

function mediaUrl(path) {
  if (!path) return "";
  const s = String(path);
  if (s.startsWith("http")) return s;
  const base = (apiClient.defaults.baseURL || "").replace(/\/$/, "");
  const p = s.startsWith("/") ? s : `/${s}`;
  return `${base}${p}`;
}

function formatMonthHeading(batch) {
  if (batch?.month_date) {
    const d = new Date(`${batch.month_date}T12:00:00`);
    if (!Number.isNaN(d.getTime())) {
      return d.toLocaleDateString("en-US", { month: "long", year: "numeric" });
    }
  }
  return batch?.month_label || "Batch";
}

function truncateFilename(name, max = 42) {
  if (!name || name.length <= max) return name || "";
  return `${name.slice(0, max - 1)}…`;
}

function formatMatchMethod(m) {
  if (!m) return "—";
  const map = {
    auto_resolved: "Auto-resolved",
    ambiguous_manual_review: "Ambiguous (manual review)",
    number_only_name_mismatch: "ID match, name mismatch",
  };
  return map[m] || m;
}

function patchDocumentInLists(job, setDocsByBatch) {
  if (!job?.id) return;
  const rows = Array.isArray(job.rows) ? job.rows : [];
  const total = rows.length;
  const resolved = rows.filter((r) => r.status === "resolved").length;
  setDocsByBatch((prev) => {
    const next = { ...prev };
    for (const batchId of Object.keys(next)) {
      const list = next[batchId];
      if (!Array.isArray(list)) continue;
      const idx = list.findIndex((d) => d.id === job.id);
      if (idx === -1) continue;
      const copy = [...list];
      copy[idx] = {
        ...copy[idx],
        rows_total: total,
        rows_resolved: resolved,
        status: job.status,
      };
      next[batchId] = copy;
    }
    return next;
  });
}

function PdfPane({ fileUrl }) {
  const [numPages, setNumPages] = useState(null);
  const containerRef = useRef(null);
  const [width, setWidth] = useState(520);
  const [zoom, setZoom] = useState(1.0);

  const zoomPct = Math.round(zoom * 100);
  const canZoomOut = zoom > 0.5;
  const canZoomIn = zoom < 2.0;

  const zoomOut = () => {
    setZoom((z) => Math.max(0.5, Math.round((z - 0.25) * 100) / 100));
  };
  const zoomIn = () => {
    setZoom((z) => Math.min(2.0, Math.round((z + 0.25) * 100) / 100));
  };
  const fitWidth = () => setZoom(1.0);

  useEffect(() => {
    const el = containerRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver((entries) => {
      for (const e of entries) {
        setWidth(Math.max(240, Math.floor(e.contentRect.width) - 16));
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const token = useMemo(() => {
    if (typeof localStorage === "undefined") return null;
    return localStorage.getItem("access");
  }, []);

  // IMPORTANT: keep `file` stable across zoom changes so `Document` doesn't reload.
  const file = useMemo(() => {
    if (!fileUrl || typeof fileUrl !== "string") return null;
    return {
      url: fileUrl,
      httpHeaders: token ? { Authorization: `Bearer ${token}` } : {},
    };
  }, [fileUrl, token]);

  const onLoadSuccess = useCallback(({ numPages: n }) => setNumPages(n), []);

  return (
    <div className="pdf-pane" ref={containerRef}>
      <div className="pdf-toolbar" role="toolbar" aria-label="PDF zoom controls">
        <button
          type="button"
          className="pdf-toolbar-btn"
          onClick={zoomOut}
          disabled={!canZoomOut}
          title="Zoom out"
        >
          −
        </button>
        <div className="pdf-toolbar-zoom" aria-label="Zoom level">
          {zoomPct}%
        </div>
        <button
          type="button"
          className="pdf-toolbar-btn"
          onClick={zoomIn}
          disabled={!canZoomIn}
          title="Zoom in"
        >
          +
        </button>
        <button
          type="button"
          className="pdf-toolbar-btn"
          onClick={fitWidth}
          title="Fit width"
        >
          Fit
        </button>
      </div>
      <div className="pdf-scroll">
        {file ? (
          <Document
            file={file}
            onLoadSuccess={onLoadSuccess}
            loading={<div className="detail-meta">Loading PDF…</div>}
            error={<div className="list-error">Could not load PDF.</div>}
          >
            {numPages
              ? Array.from({ length: numPages }, (_, i) => (
                  <div className="detail-pdf-page-wrap" key={i + 1}>
                    <Page
                      pageNumber={i + 1}
                      width={Math.floor(width * zoom)}
                      loading={null}
                      renderTextLayer={false}
                      renderAnnotationLayer={false}
                    />
                  </div>
                ))
              : null}
          </Document>
        ) : (
          <div className="detail-meta">No PDF file.</div>
        )}
      </div>
    </div>
  );
}

const STATUS_BADGE = {
  queued: { bg: "#6b7280", fg: "#fff", label: "Queued" },
  processing: { bg: "#f59e0b", fg: "#111", label: "Processing" },
  needs_review: { bg: "#ea580c", fg: "#fff", label: "Needs review" },
  resolved: { bg: "#16a34a", fg: "#fff", label: "Resolved" },
  error: { bg: "#dc2626", fg: "#fff", label: "Error" },
};

function StatusBadge({ status }) {
  const cfg = STATUS_BADGE[status] || STATUS_BADGE.queued;
  return (
    <span
      className="status-badge"
      style={{ backgroundColor: cfg.bg, color: cfg.fg }}
    >
      {cfg.label}
    </span>
  );
}

function Spinner({ message }) {
  return (
    <div className="spinner-wrap" aria-live="polite">
      <div className="spinner" />
      <p className="spinner-text">{message}</p>
    </div>
  );
}

function IconDocuments() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6z"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
      <path
        d="M14 2v6h6M16 13H8M16 17H8M10 9H8"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

function IconReports() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M4 19V5M4 19h16M8 17V9m4 8V7m4 10v-4"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

function IconSettings() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z"
        stroke="currentColor"
        strokeWidth="1.5"
      />
      <path
        d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06A1.65 1.65 0 0 0 15 19.4a1.65 1.65 0 0 0-1 .73 1.65 1.65 0 0 0-.11 1.84 2 2 0 1 1-3.48 2.05 1.65 1.65 0 0 0-1.82-.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.6 15a1.65 1.65 0 0 0-.73-1 1.65 1.65 0 0 0-1.84-.11 2 2 0 1 1 2.05-3.48 1.65 1.65 0 0 0 .33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6a1.65 1.65 0 0 0 1-.73 1.65 1.65 0 0 0 .11-1.84 2 2 0 1 1 3.48-2.05 1.65 1.65 0 0 0 1.82.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9c.3-.53.98-.85 1.84-.11a2 2 0 1 1-2.05 3.48 1.65 1.65 0 0 0-.33 1.82z"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinecap="round"
      />
    </svg>
  );
}

function RowReviewCard({ row, jobId, onRefresh, documentLocked }) {
  const re = row.resolved_employee;
  const [finalName, setFinalName] = useState(
    () => re?.full_name ?? row.ocr_name_raw ?? "",
  );
  const [finalId, setFinalId] = useState(
    () => re?.employee_id ?? row.ocr_id_clean ?? "",
  );
  const [selectedEmployeePk, setSelectedEmployeePk] = useState(
    () => re?.id ?? null,
  );
  const [selectedCandidateIdx, setSelectedCandidateIdx] = useState(null);
  const [idSearchQuery, setIdSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchLoading, setSearchLoading] = useState(false);
  const [resolveBusy, setResolveBusy] = useState(false);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [justSaved, setJustSaved] = useState(false);

  const searchWrapRef = useRef(null);

  const isResolved = row.status === "resolved";
  const isManual = row.added_manually;
  const locked = Boolean(documentLocked);
  const savedEmployeePk = row.resolved_employee?.id ?? null;
  const selectionChanged =
    !locked &&
    savedEmployeePk != null &&
    selectedEmployeePk != null &&
    selectedEmployeePk !== savedEmployeePk;

  useEffect(() => {
    const re2 = row.resolved_employee;
    setFinalName(re2?.full_name ?? row.ocr_name_raw ?? "");
    setFinalId(re2?.employee_id ?? row.ocr_id_clean ?? "");
    setSelectedEmployeePk(re2?.id ?? null);
    setSelectedCandidateIdx(null);
    setIdSearchQuery("");
    setSearchResults([]);
    setSearchOpen(false);
    setJustSaved(false);
  }, [row.id, row.status, row.resolved_at, row.resolved_employee?.id]);

  useEffect(() => {
    if (!justSaved) return undefined;
    const t = setTimeout(() => setJustSaved(false), 1400);
    return () => clearTimeout(t);
  }, [justSaved]);

  useEffect(() => {
    function onDocMouseDown(e) {
      if (!searchOpen) return;
      if (searchWrapRef.current && !searchWrapRef.current.contains(e.target)) {
        setSearchOpen(false);
      }
    }
    document.addEventListener("mousedown", onDocMouseDown);
    return () => document.removeEventListener("mousedown", onDocMouseDown);
  }, [searchOpen]);

  useEffect(() => {
    const q = idSearchQuery.replace(/\D/g, "");
    if (!q.length) {
      setSearchResults([]);
      setSearchLoading(false);
      return;
    }
    setSearchLoading(true);
    const ac = new AbortController();
    const t = setTimeout(async () => {
      try {
        const { data } = await apiClient.get("/api/employees/search/", {
          params: { q },
          signal: ac.signal,
        });
        const list = Array.isArray(data) ? data : [];
        setSearchResults(list.slice(0, 8));
        setSearchOpen(true);
      } catch (err) {
        if (err.code !== "ERR_CANCELED" && err.name !== "CanceledError") {
          setSearchResults([]);
        }
      } finally {
        setSearchLoading(false);
      }
    }, 300);
    return () => {
      clearTimeout(t);
      ac.abort();
    };
  }, [idSearchQuery]);

  const top3 = Array.isArray(row.top_candidates)
    ? row.top_candidates.slice(0, 3)
    : [];

  const rowLabel = Number.isFinite(Number(row.row_index))
    ? `Row ${Number(row.row_index) + 1}`
    : `Row ${row.row_index}`;

  const conf = Number(row.confidence ?? 0).toFixed(1);

  async function pickCandidate(c, idx) {
    if (locked) return;
    let pk = c.id ?? null;
    if (pk == null && c.employee_id) {
      try {
        const digits = String(c.employee_id).replace(/\D/g, "");
        const { data } = await apiClient.get("/api/employees/search/", {
          params: { q: digits || c.employee_id },
        });
        const list = Array.isArray(data) ? data : [];
        const exact = list.find((e) => e.employee_id === String(c.employee_id));
        pk = exact?.id ?? null;
      } catch {
        pk = null;
      }
    }
    setSelectedEmployeePk(pk);
    setFinalName(c.full_name ?? "");
    setFinalId(c.employee_id ?? "");
    setSelectedCandidateIdx(idx);
    setSearchOpen(false);
  }

  function pickSearchResult(emp) {
    if (locked) return;
    setSelectedEmployeePk(emp.id);
    setFinalName(emp.full_name ?? "");
    setFinalId(emp.employee_id ?? "");
    setSelectedCandidateIdx(null);
    setSearchOpen(false);
    setIdSearchQuery("");
  }

  async function resolveEmployeePkFromForm() {
    if (selectedEmployeePk) return selectedEmployeePk;
    const digits = finalId.replace(/\D/g, "");
    if (!digits) return null;
    const { data } = await apiClient.get("/api/employees/search/", {
      params: { q: digits },
    });
    const list = Array.isArray(data) ? data : [];
    const exact = list.find((e) => e.employee_id === digits);
    if (exact) return exact.id;
    if (list.length === 1) return list[0].id;
    return null;
  }

  async function onResolve() {
    if (locked) return;
    setResolveBusy(true);
    try {
      const pk = await resolveEmployeePkFromForm();
      if (!pk) {
        window.alert(
          "Select a candidate, pick from search, or enter a valid employee ID.",
        );
        return;
      }
      await apiClient.patch(`/api/documents/${jobId}/rows/${row.id}/resolve/`, {
        resolved_employee: pk,
      });
      await onRefresh();
      setJustSaved(true);
    } catch (e) {
      window.alert(e.response?.data?.detail || e.message || "Resolve failed.");
    } finally {
      setResolveBusy(false);
    }
  }

  async function onDelete() {
    if (!row.added_manually) return;
    if (locked) return;
    if (!window.confirm("Delete this manually added row?")) return;
    setDeleteBusy(true);
    try {
      await apiClient.delete(`/api/documents/${jobId}/rows/${row.id}/`);
      await onRefresh();
    } catch (e) {
      window.alert(e.response?.data?.detail || e.message || "Delete failed.");
    } finally {
      setDeleteBusy(false);
    }
  }

  function candidateSelectedClass(c, idx) {
    const byIdx = selectedCandidateIdx === idx;
    const byPk =
      selectedEmployeePk != null &&
      c.id != null &&
      c.id === selectedEmployeePk;
    if (!(byIdx || byPk)) return "";
    return selectionChanged ? " selected dirty" : " selected";
  }

  return (
    <div className={`row-review-card${isManual ? " row-review-card--manual" : ""}`}>
      <div className="row-review-header">
        <strong>
          {rowLabel}
          {isResolved ? (
            <span className="row-resolved-check" title="Row resolved">
              {" "}
              ✓
            </span>
          ) : null}
        </strong>
        {!isManual ? (
          <>
            {" · "}
            OCR: {row.ocr_name_raw || "—"} /{" "}
            {row.ocr_id_clean || row.ocr_id_raw || "—"}
            {" · "}
            Confidence: <strong>{conf}%</strong>
            {" · "}
            Method: <strong>{formatMatchMethod(row.match_method)}</strong>
          </>
        ) : (
          <>
            {" · "}
            <span className="row-manual-muted">Manually added — use Search ID</span>
          </>
        )}
      </div>

      {isManual ? (
        <div className="row-review-crops">
          <div className="row-review-crop">
            <div className="row-review-crop-placeholder">Manually added</div>
          </div>
          <div className="row-review-crop">
            <div className="row-review-crop-placeholder">Manually added</div>
          </div>
        </div>
      ) : (
        <div className="row-review-crops">
          <div className="row-review-crop">
            {row.name_crop ? (
              <img src={mediaUrl(row.name_crop)} alt="Name crop" />
            ) : (
              <div className="row-review-crop-placeholder">No name crop</div>
            )}
          </div>
          <div className="row-review-crop">
            {row.id_crop ? (
              <img src={mediaUrl(row.id_crop)} alt="ID crop" />
            ) : (
              <div className="row-review-crop-placeholder">No ID crop</div>
            )}
          </div>
        </div>
      )}

      {!isManual && top3.length > 0 ? (
        <div className="row-review-candidates">
          {top3.map((c, idx) => (
            <button
              key={c.id ?? `${c.employee_id}-${idx}`}
              type="button"
              className={`candidate-tile${candidateSelectedClass(c, idx)}`}
              onClick={
                locked
                  ? undefined
                  : () => {
                      void pickCandidate(c, idx);
                    }
              }
              aria-disabled={locked ? "true" : undefined}
              tabIndex={locked ? -1 : 0}
            >
              <div className="emp-id">{c.employee_id}</div>
              <div className="emp-name">{c.full_name}</div>
              <div className="emp-score">
                Total score: {Number(c.total_score ?? 0).toFixed(1)}%
              </div>
            </button>
          ))}
        </div>
      ) : null}

      <div className="row-review-fields">
        <div>
          <label htmlFor={`fn-${row.id}`}>Name (final)</label>
          <input
            id={`fn-${row.id}`}
            type="text"
            value={finalName}
            disabled={locked}
            onChange={(e) => setFinalName(e.target.value)}
          />
        </div>
        <div>
          <label htmlFor={`fid-${row.id}`}>ID (final)</label>
          <input
            id={`fid-${row.id}`}
            type="text"
            value={finalId}
            disabled={locked}
            onChange={(e) => setFinalId(e.target.value)}
          />
        </div>
        <div ref={searchWrapRef} className="id-search-wrap">
          <label htmlFor={`sid-${row.id}`}>Search ID</label>
          <input
            id={`sid-${row.id}`}
            type="text"
            inputMode="numeric"
            autoComplete="off"
            placeholder="Type digits…"
            value={idSearchQuery}
            disabled={locked}
            onChange={(e) => setIdSearchQuery(e.target.value)}
            onFocus={() => {
              const q = idSearchQuery.replace(/\D/g, "");
              if (q.length && searchResults.length) setSearchOpen(true);
            }}
          />
          {searchOpen && searchResults.length > 0 ? (
            <div className="id-search-dropdown" role="listbox">
              {searchResults.map((emp) => (
                <button
                  key={emp.id}
                  type="button"
                  className="id-search-item"
                  role="option"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => pickSearchResult(emp)}
                >
                  <div className="emp-id">{emp.employee_id}</div>
                  <div className="emp-name">{emp.full_name}</div>
                </button>
              ))}
            </div>
          ) : null}
          {searchLoading ? (
            <div style={{ fontSize: "0.7rem", color: "#64748b", marginTop: 4 }}>
              Searching…
            </div>
          ) : null}
        </div>
      </div>

      <div className="row-review-actions">
        <button
          type="button"
          className={`btn-resolve${
            locked
              ? " btn-resolve--locked"
              : savedEmployeePk != null
                ? selectionChanged
                  ? " btn-resolve--dirty"
                  : " btn-resolve--uptodate"
                : ""
          }`}
          disabled={
            locked ||
            resolveBusy ||
            (savedEmployeePk != null && !selectionChanged)
          }
          onClick={onResolve}
        >
          {resolveBusy ? (
            savedEmployeePk != null ? (
              "Saving…"
            ) : (
              "Resolving…"
            )
          ) : savedEmployeePk != null ? (
            selectionChanged ? (
              "Save change"
            ) : (
              "Up to date"
            )
          ) : (
            "Resolve"
          )}
          {justSaved ? <span className="save-check"> ✓</span> : null}
        </button>
        {selectionChanged ? (
          <div className="unsaved-hint">Unsaved change</div>
        ) : null}
        <button
          type="button"
          className="btn-delete-row"
          disabled={locked || !row.added_manually || deleteBusy}
          title={
            row.added_manually
              ? "Delete this manually added row"
              : "Only manually added rows can be deleted"
          }
          onClick={onDelete}
        >
          {deleteBusy ? "…" : "Delete"}
        </button>
      </div>
    </div>
  );
}

export default function DocumentsPage() {
  const [batches, setBatches] = useState([]);
  const [batchesError, setBatchesError] = useState("");
  const [openBatchIds, setOpenBatchIds] = useState(() => new Set());
  const [docsByBatch, setDocsByBatch] = useState({});
  const [docsLoading, setDocsLoading] = useState({});
  const [docsError, setDocsError] = useState({});

  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [rerunBusy, setRerunBusy] = useState(false);

  const uploadInputRef = useRef(null);
  const [uploadBatchId, setUploadBatchId] = useState(null);
  const [uploadBusy, setUploadBusy] = useState(false);
  const [submitBusy, setSubmitBusy] = useState(false);
  const [addRowBusy, setAddRowBusy] = useState(false);
  const [reopenBusy, setReopenBusy] = useState(false);

  const loadBatches = useCallback(async () => {
    setBatchesError("");
    try {
      const { data } = await apiClient.get("/api/batches/");
      setBatches(normalizeList(data));
    } catch (e) {
      setBatchesError(
        e.response?.data?.detail || e.message || "Failed to load batches.",
      );
    }
  }, []);

  const loadBatchDocuments = useCallback(async (batchId) => {
    setDocsLoading((m) => ({ ...m, [batchId]: true }));
    setDocsError((m) => ({ ...m, [batchId]: "" }));
    try {
      const { data } = await apiClient.get("/api/documents/", {
        params: { batch: batchId },
      });
      setDocsByBatch((prev) => ({ ...prev, [batchId]: normalizeList(data) }));
    } catch (e) {
      setDocsByBatch((prev) => ({ ...prev, [batchId]: [] }));
      setDocsError((m) => ({
        ...m,
        [batchId]:
          e.response?.data?.detail || e.message || "Failed to load documents.",
      }));
    } finally {
      setDocsLoading((m) => ({ ...m, [batchId]: false }));
    }
  }, []);

  useEffect(() => {
    loadBatches();
  }, [loadBatches]);

  useEffect(() => {
    if (!batches.length) return;
    setOpenBatchIds((prev) => {
      if (prev.size > 0) return prev;
      return new Set([batches[0].id]);
    });
  }, [batches]);

  useEffect(() => {
    openBatchIds.forEach((id) => {
      if (docsByBatch[id] === undefined && !docsLoading[id]) {
        loadBatchDocuments(id);
      }
    });
  }, [openBatchIds, batches, docsByBatch, docsLoading, loadBatchDocuments]);

  const fetchDetail = useCallback(async (jobId) => {
    if (!jobId) {
      setDetail(null);
      return;
    }
    setDetailLoading(true);
    setDetailError("");
    try {
      const { data } = await apiClient.get(`/api/documents/${jobId}/`);
      setDetail(data);
      patchDocumentInLists(data, setDocsByBatch);
    } catch (e) {
      setDetailError(
        e.response?.data?.detail || e.message || "Failed to load document.",
      );
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    setDetail(null);
    fetchDetail(selectedId);
  }, [selectedId, fetchDetail]);

  useEffect(() => {
    if (!selectedId || !detail) return;
    const s = detail.status;
    if (s !== "queued" && s !== "processing") return;
    const t = setInterval(() => {
      fetchDetail(selectedId);
    }, 2500);
    return () => clearInterval(t);
  }, [selectedId, detail?.status, fetchDetail]);

  const toggleBatch = (batchId) => {
    setOpenBatchIds((prev) => {
      const next = new Set(prev);
      if (next.has(batchId)) next.delete(batchId);
      else {
        next.add(batchId);
        if (docsByBatch[batchId] === undefined) {
          loadBatchDocuments(batchId);
        }
      }
      return next;
    });
  };

  const openUpload = (batchId) => {
    setUploadBatchId(batchId);
    requestAnimationFrame(() => uploadInputRef.current?.click());
  };

  const onUploadFiles = async (e) => {
    const files = e.target.files;
    const batchId = uploadBatchId;
    e.target.value = "";
    if (!files?.length || batchId == null) return;
    setUploadBusy(true);
    try {
      const fd = new FormData();
      fd.append("batch_id", String(batchId));
      for (let i = 0; i < files.length; i += 1) {
        fd.append("files", files[i]);
      }
      await apiClient.post("/api/documents/upload/", fd);
      await loadBatchDocuments(batchId);
      await loadBatches();
    } catch (err) {
      const msg =
        err.response?.data?.detail ||
        (Array.isArray(err.response?.data?.errors) &&
          err.response.data.errors[0]?.detail) ||
        err.message ||
        "Upload failed.";
      window.alert(typeof msg === "string" ? msg : "Upload failed.");
    } finally {
      setUploadBusy(false);
      setUploadBatchId(null);
    }
  };

  const onRerun = async () => {
    if (!detail?.id) return;
    setRerunBusy(true);
    try {
      const { data } = await apiClient.post(`/api/documents/${detail.id}/rerun/`);
      setDetail(data);
      patchDocumentInLists(data, setDocsByBatch);
      if (detail.batch_id != null) {
        await loadBatchDocuments(detail.batch_id);
      }
    } catch (e) {
      window.alert(
        e.response?.data?.detail || e.message || "Re-run request failed.",
      );
    } finally {
      setRerunBusy(false);
    }
  };

  const renderDetail = () => {
    if (!selectedId) {
      return (
        <div className="detail-empty">Select a document to view details</div>
      );
    }
    if (detailLoading && !detail) {
      return <Spinner message="Loading document…" />;
    }
    if (detailError) {
      return <div className="list-error">{detailError}</div>;
    }
    if (!detail) return null;

    if (detail.status === "queued") {
      return <Spinner message="Queued — waiting to process…" />;
    }
    if (detail.status === "processing") {
      return <Spinner message="Processing document…" />;
    }

    if (detail.status === "error") {
      return (
        <div>
          <h2 className="detail-section">{truncateFilename(detail.filename, 80)}</h2>
          <div className="error-box">
            {detail.error_message || "An error occurred while processing this file."}
          </div>
          <button
            type="button"
            className="rerun-btn"
            disabled={rerunBusy}
            onClick={onRerun}
          >
            {rerunBusy ? "Re-running…" : "Re-run"}
          </button>
        </div>
      );
    }

    if (detail.status === "needs_review" || detail.status === "resolved") {
      const rows = Array.isArray(detail.rows) ? detail.rows : [];
      const total = rows.length;
      const resolvedCount = rows.filter((r) => r.status === "resolved").length;
      const allRowsResolved = total > 0 && resolvedCount === total;
      const docResolved = detail.status === "resolved";

      const handleRefresh = async () => {
        await fetchDetail(selectedId);
      };

      const handleSubmitDocument = async () => {
        setSubmitBusy(true);
        try {
          const { data } = await apiClient.post(
            `/api/documents/${detail.id}/submit/`,
          );
          setDetail(data);
          patchDocumentInLists(data, setDocsByBatch);
        } catch (e) {
          window.alert(
            e.response?.data?.detail || e.message || "Submit failed.",
          );
        } finally {
          setSubmitBusy(false);
        }
      };

      const handleAddPerson = async () => {
        setAddRowBusy(true);
        try {
          await apiClient.post(`/api/documents/${detail.id}/rows/add/`, {});
          await fetchDetail(selectedId);
        } catch (e) {
          window.alert(
            e.response?.data?.detail || e.message || "Could not add row.",
          );
        } finally {
          setAddRowBusy(false);
        }
      };

      const handleReopen = async () => {
        setReopenBusy(true);
        try {
          const { data } = await apiClient.post(
            `/api/documents/${detail.id}/reopen/`,
          );
          setDetail(data);
          patchDocumentInLists(data, setDocsByBatch);
        } catch (e) {
          window.alert(
            e.response?.data?.detail || e.message || "Reopen failed.",
          );
        } finally {
          setReopenBusy(false);
        }
      };

      const pdfSrc = detail.file ? mediaUrl(detail.file) : "";

      return (
        <div className="detail-split-root">
          <div className="detail-split-toolbar">
            <h2 className="detail-split-title">
              {truncateFilename(detail.filename, 120)}
            </h2>
            <div className="detail-meta">
              Status: <StatusBadge status={detail.status} />
            </div>
          </div>
          <div className="detail-split">
            <div className="detail-split-left">
              <PdfPane fileUrl={pdfSrc} />
            </div>
            <div className="detail-split-right">
              <div className="detail-split-right-scroll">
                {docResolved ? (
                  <div className="review-lock-banner">
                    <button
                      type="button"
                      className="btn-unlock"
                      disabled={reopenBusy}
                      onClick={handleReopen}
                    >
                      {reopenBusy ? "Unlocking…" : "Unlock for editing"}
                    </button>
                    <div className="review-lock-hint">
                      This document has been submitted. Unlocking will remove its
                      HPRecords so you can edit and resubmit.
                    </div>
                  </div>
                ) : null}
                <div className="review-rows">
                  {rows.length === 0 ? (
                    <p className="detail-meta">No rows recorded.</p>
                  ) : (
                    rows.map((row) => (
                      <RowReviewCard
                        key={row.id}
                        row={row}
                        jobId={detail.id}
                        onRefresh={handleRefresh}
                        documentLocked={docResolved}
                      />
                    ))
                  )}
                </div>
                <div className="review-panel-footer">
                  {docResolved ? (
                    <p className="submit-hint submit-hint--done">
                      Document submitted — all rows are locked in for this month.
                    </p>
                  ) : allRowsResolved ? (
                    <button
                      type="button"
                      className="btn-submit-document"
                      disabled={submitBusy}
                      onClick={handleSubmitDocument}
                    >
                      {submitBusy ? "Submitting…" : "Submit Document"}
                    </button>
                  ) : total === 0 ? (
                    <p className="submit-hint submit-hint--pending">
                      No rows yet — wait for processing or use + Add person.
                    </p>
                  ) : (
                    <p className="submit-hint submit-hint--pending">
                      {resolvedCount} of {total} rows resolved — resolve all rows
                      to submit
                    </p>
                  )}
                  <button
                    type="button"
                    className="btn-add-person"
                    disabled={addRowBusy || docResolved}
                    onClick={handleAddPerson}
                  >
                    {addRowBusy ? "Adding…" : "+ Add person"}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      );
    }

    return (
      <div>
        <h2>{truncateFilename(detail.filename, 120)}</h2>
        <p className="detail-meta">
          Status: <StatusBadge status={detail.status} />
        </p>
      </div>
    );
  };

  return (
    <div className="documents-layout">
      <input
        ref={uploadInputRef}
        type="file"
        accept="application/pdf,.pdf"
        multiple
        hidden
        onChange={onUploadFiles}
      />

      <aside className="documents-iconbar" aria-label="Main navigation">
        <button
          type="button"
          className="active"
          title="Documents"
          aria-current="page"
        >
          <IconDocuments />
        </button>
        <button type="button" disabled title="Reports (coming soon)">
          <IconReports />
        </button>
        <button type="button" disabled title="Settings (coming soon)">
          <IconSettings />
        </button>
      </aside>

      <section className="documents-list-panel" aria-label="Documents list">
        <div className="documents-list-header">
          <h1>Documents</h1>
          <button
            type="button"
            className="upload-btn"
            disabled={uploadBusy || !batches.length}
            title={
              batches.length
                ? "Upload into the first month batch"
                : "Create a month batch first"
            }
            onClick={() => batches[0] && openUpload(batches[0].id)}
          >
            {uploadBusy ? "…" : "Upload"}
          </button>
        </div>
        <div className="documents-list-scroll">
          {batchesError ? (
            <div className="list-error">{batchesError}</div>
          ) : null}
          {!batches.length && !batchesError ? (
            <div className="list-error">No month batches yet.</div>
          ) : null}
          {batches.map((batch) => {
            const open = openBatchIds.has(batch.id);
            const docs = docsByBatch[batch.id];
            const loading = docsLoading[batch.id];
            const err = docsError[batch.id];
            return (
              <div key={batch.id} className="batch-block">
                <button
                  type="button"
                  className="batch-summary-btn"
                  onClick={() => toggleBatch(batch.id)}
                  aria-expanded={open}
                >
                  <div className="batch-summary-inner">
                    <span className="batch-chevron">{open ? "▾" : "▸"}</span>
                    <span style={{ flex: 1 }}>{formatMonthHeading(batch)}</span>
                    <span className="batch-summary-meta">
                      {batch.document_count != null ? batch.document_count : "—"} docs
                    </span>
                  </div>
                </button>
                {open ? (
                  <>
                    <div className="batch-toolbar">
                      <button
                        type="button"
                        className="upload-btn"
                        disabled={uploadBusy}
                        onClick={() => openUpload(batch.id)}
                      >
                        Upload to month
                      </button>
                    </div>
                    {loading ? (
                      <div className="list-error">Loading…</div>
                    ) : null}
                    {err ? <div className="list-error">{err}</div> : null}
                    {docs && !loading
                      ? docs.map((doc) => (
                          <div
                            key={doc.id}
                            role="button"
                            tabIndex={0}
                            className={`doc-item${selectedId === doc.id ? " selected" : ""}`}
                            onClick={() => setSelectedId(doc.id)}
                            onKeyDown={(ev) => {
                              if (ev.key === "Enter" || ev.key === " ") {
                                ev.preventDefault();
                                setSelectedId(doc.id);
                              }
                            }}
                          >
                            <div className="doc-item-row1">
                              <span className="doc-item-name" title={doc.filename}>
                                {truncateFilename(doc.filename)}
                              </span>
                              <StatusBadge status={doc.status} />
                            </div>
                            <div className="doc-item-meta">
                              Rows {doc.rows_resolved ?? 0}/{doc.rows_total ?? 0}
                            </div>
                          </div>
                        ))
                      : null}
                    {docs && !docs.length && !loading && !err ? (
                      <div className="list-error">No documents in this batch.</div>
                    ) : null}
                  </>
                ) : null}
              </div>
            );
          })}
        </div>
      </section>

      <main
        className={`documents-detail${
          detail &&
          (detail.status === "needs_review" || detail.status === "resolved")
            ? " documents-detail--split"
            : ""
        }`}
        aria-label="Document details"
      >
        {renderDetail()}
      </main>
    </div>
  );
}
