import { useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";

const API_BASE = "http://localhost:8000";

export default function LoginPage() {
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    try {
      const { data } = await axios.post(`${API_BASE}/api/auth/token/`, {
        username,
        password,
      });
      if (data.access) {
        localStorage.setItem("access", data.access);
      }
      if (data.refresh) {
        localStorage.setItem("refresh", data.refresh);
      }
      if (data.role != null) {
        localStorage.setItem("role", String(data.role));
      }
      navigate("/", { replace: true });
    } catch (err) {
      const detail =
        err.response?.data?.detail ||
        err.response?.data?.non_field_errors?.[0] ||
        "Login failed.";
      setError(typeof detail === "string" ? detail : "Login failed.");
    }
  }

  return (
    <div className="app-shell">
      <div className="card">
        <h1 style={{ marginTop: 0 }}>Sign in</h1>
        <form onSubmit={handleSubmit}>
          {error ? <div className="error">{error}</div> : null}
          <label htmlFor="username">Username</label>
          <input
            id="username"
            name="username"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
          />
          <label htmlFor="password">Password</label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
          <button type="submit">Log in</button>
        </form>
      </div>
    </div>
  );
}
