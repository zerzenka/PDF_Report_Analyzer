import { useCallback, useEffect, useRef, useState } from "react";
import { apiClient } from "../api/client.js";
import "./DocumentsPage.css";

function normalizeList(data) {
  if (Array.isArray(data)) return data;
  if (data && Array.isArray(data.results)) return data.results;
  return [];
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
      return (
        <div>
          <div className="detail-section">
            <h2>{truncateFilename(detail.filename, 120)}</h2>
            <div className="detail-meta">
              Status: <StatusBadge status={detail.status} />
            </div>
          </div>
          <table className="rows-table">
            <thead>
              <tr>
                <th>#</th>
                <th>OCR name (raw)</th>
                <th>OCR ID (clean)</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={3}>No rows recorded.</td>
                </tr>
              ) : (
                rows.map((row) => (
                  <tr key={row.id}>
                    <td>{row.row_index}</td>
                    <td>{row.ocr_name_raw || "—"}</td>
                    <td>{row.ocr_id_clean || "—"}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
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

      <main className="documents-detail" aria-label="Document details">
        {renderDetail()}
      </main>
    </div>
  );
}
