import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { apiClient } from "../api/client.js";
import "./ReportsPage.css";

function monthLabelToDisplay(label) {
  const m = /^(\d{2})-(\d{4})$/.exec(String(label || ""));
  if (!m) return label || "";
  const mm = Number(m[1]);
  const yyyy = Number(m[2]);
  const d = new Date(Date.UTC(yyyy, mm - 1, 1));
  return d.toLocaleDateString("en-US", { month: "short", year: "numeric" });
}

function downloadBlob(filename, blob) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
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

export default function ReportsPage() {
  const navigate = useNavigate();
  const [departments, setDepartments] = useState([]);
  const [departmentId, setDepartmentId] = useState("");
  const [batches, setBatches] = useState([]);
  const [monthLabel, setMonthLabel] = useState("");

  const [monthly, setMonthly] = useState(null);
  const [monthlyLoading, setMonthlyLoading] = useState(false);
  const [monthlyError, setMonthlyError] = useState("");

  const [trend, setTrend] = useState([]);
  const [trendError, setTrendError] = useState("");

  useEffect(() => {
    async function load() {
      const [deptRes, batchRes] = await Promise.all([
        apiClient.get("/api/employees/departments/"),
        apiClient.get("/api/batches/"),
      ]);
      const depts = Array.isArray(deptRes.data) ? deptRes.data : [];
      setDepartments(depts);
      const firstDept = depts[0]?.id ? String(depts[0].id) : "";
      setDepartmentId((prev) => prev || firstDept);

      const bs = Array.isArray(batchRes.data) ? batchRes.data : batchRes.data?.results || [];
      setBatches(bs);
    }
    load().catch(() => {
      setDepartments([]);
      setBatches([]);
    });
  }, []);

  const monthOptions = useMemo(() => {
    if (!departmentId) return [];
    const deptBatches = batches.filter((b) => String(b.department) === String(departmentId));
    const labels = deptBatches.map((b) => b.month_label).filter(Boolean);
    // de-dup, preserve order
    return [...new Set(labels)];
  }, [batches, departmentId]);

  useEffect(() => {
    if (!monthLabel && monthOptions.length) {
      setMonthLabel(monthOptions[0]);
    }
  }, [monthLabel, monthOptions]);

  useEffect(() => {
    if (!departmentId) return;
    setTrendError("");
    apiClient
      .get("/api/reports/monthly/trend/", { params: { department: departmentId } })
      .then(({ data }) => setTrend(Array.isArray(data) ? data : []))
      .catch((e) => setTrendError(e.response?.data?.detail || e.message || "Failed to load trend."));
  }, [departmentId]);

  useEffect(() => {
    if (!departmentId || !monthLabel) return;
    setMonthlyLoading(true);
    setMonthlyError("");
    apiClient
      .get("/api/reports/monthly/", {
        params: { department: departmentId, month: monthLabel },
      })
      .then(({ data }) => setMonthly(data))
      .catch((e) => {
        setMonthly(null);
        setMonthlyError(e.response?.data?.detail || e.message || "Failed to load report.");
      })
      .finally(() => setMonthlyLoading(false));
  }, [departmentId, monthLabel]);

  async function onExport() {
    if (!departmentId || !monthLabel) return;
    const res = await apiClient.get("/api/reports/monthly/export/", {
      params: { department: departmentId, month: monthLabel },
      responseType: "blob",
    });
    downloadBlob(`monthly_report_${monthLabel}.xlsx`, res.data);
  }

  const items = Array.isArray(monthly?.items) ? monthly.items : [];
  const totalParticipations = monthly?.summary?.total_participations ?? 0;

  const chartData = trend.map((r) => ({
    month: monthLabelToDisplay(r.month_label),
    total_documents: r.total_documents ?? 0,
    unique_persons: r.unique_persons ?? 0,
  }));

  return (
    <div className="reports-layout">
      <aside className="documents-iconbar" aria-label="Main navigation">
        <button type="button" title="Documents" onClick={() => navigate("/")}>
          <IconDocuments />
        </button>
        <button
          type="button"
          className="active"
          title="Reports"
          aria-current="page"
        >
          <IconReports />
        </button>
      </aside>

      <main className="reports-main">
        <div className="reports-header">
          <h1>Monthly Reports</h1>
          <div className="reports-controls">
            <div className="control">
              <label>Department</label>
              <select
                value={departmentId}
                onChange={(e) => {
                  setDepartmentId(e.target.value);
                  setMonthLabel("");
                }}
              >
                {departments.map((d) => (
                  <option key={d.id} value={String(d.id)}>
                    {d.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="control">
              <label>Month</label>
              <select value={monthLabel} onChange={(e) => setMonthLabel(e.target.value)}>
                {monthOptions.map((m) => (
                  <option key={m} value={m}>
                    {monthLabelToDisplay(m)}
                  </option>
                ))}
              </select>
            </div>
            <div className="control export">
              <label>&nbsp;</label>
              <button type="button" onClick={onExport} disabled={!monthLabel || !departmentId}>
                Export to Excel
              </button>
            </div>
          </div>
        </div>

        {monthlyLoading ? <div className="reports-note">Loading…</div> : null}
        {monthlyError ? <div className="reports-error">{monthlyError}</div> : null}

        <div className="reports-table-wrap">
          <table className="reports-table">
            <thead>
              <tr>
                <th>Employee ID</th>
                <th>Full Name</th>
                <th>Department</th>
                <th style={{ textAlign: "right" }}>HP Count</th>
              </tr>
            </thead>
            <tbody>
              {items.length ? (
                items.map((r) => (
                  <tr key={`${r.employee_id}-${r.type}`}>
                    <td>{r.employee_id}</td>
                    <td>{r.full_name}</td>
                    <td>{r.department_name}</td>
                    <td style={{ textAlign: "right" }}>{r.hp_count}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={4} className="reports-empty">
                    No data.
                  </td>
                </tr>
              )}
            </tbody>
            <tfoot>
              <tr>
                <td colSpan={3} style={{ fontWeight: 700 }}>
                  Total participations
                </td>
                <td style={{ textAlign: "right", fontWeight: 700 }}>
                  {totalParticipations}
                </td>
              </tr>
            </tfoot>
          </table>
        </div>

        <div className="reports-charts">
          <div className="chart-card">
            <h2>HP Briefings per Month</h2>
            {trendError ? <div className="reports-error">{trendError}</div> : null}
            <div className="chart-area">
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="month" />
                  <YAxis allowDecimals={false} />
                  <Tooltip />
                  <Bar dataKey="total_documents" fill="#2563eb" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
          <div className="chart-card">
            <h2>Unique Participants per Month</h2>
            <div className="chart-area">
              <ResponsiveContainer width="100%" height={260}>
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="month" />
                  <YAxis />
                  <Tooltip />
                  <Line type="monotone" dataKey="unique_persons" stroke="#16a34a" strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

