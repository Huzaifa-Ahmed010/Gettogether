import { type FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { loginAccount, registerAccount } from "../api/client";
import { useAuth } from "../components/AuthContext";
import SiteLayout from "../components/SiteLayout";

export default function LoginPage() {
  const navigate = useNavigate();
  const { user, saveSession, signOut } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      if (mode === "register") {
        const response = await registerAccount({ email, password });
        saveSession(response);
        navigate("/");
        return;
      }
      const response = await loginAccount({ email, password });
      saveSession(response);
      navigate("/");
    } catch (reason) {
      const message = reason instanceof Error ? reason.message.replace(/^API error \d+: /, "") : "Unable to access your account.";
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  if (user) {
    return <SiteLayout>
      <main className="message-page content">
        <p className="eyebrow">YOUR GETTOGETHER ACCOUNT</p>
        <h1>Welcome, {user.name}</h1>
        <p>{user.email}</p>
        <button className="primary-link" onClick={() => { signOut(); navigate("/"); }}>Sign out</button>
      </main>
    </SiteLayout>;
  }

  return <SiteLayout>
    <main className="account-page content">
      <p className="eyebrow">YOUR GETTOGETHER ACCOUNT</p>
      <h1>{mode === "login" ? "Welcome back" : "Create your account"}</h1>
      <p className="directory-intro">Sign in to your GetTogether account or create one to get started.</p>
      <div className="account-tabs" role="tablist" aria-label="Account access">
        <button type="button" role="tab" aria-selected={mode === "login"} onClick={() => { setMode("login"); setError(""); }}>Sign in</button>
        <button type="button" role="tab" aria-selected={mode === "register"} onClick={() => { setMode("register"); setError(""); }}>Create account</button>
      </div>
      <form className="account-form" onSubmit={submit}>
        <label>Email address<input type="email" autoComplete="email" required maxLength={254} value={email} onChange={(event) => setEmail(event.target.value)} /></label>
        <label>Password<input type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} required minLength={mode === "register" ? 12 : 1} maxLength={128} value={password} onChange={(event) => setPassword(event.target.value)} />{mode === "register" && <small>Use at least 12 characters.</small>}</label>
        {error && <p className="account-error" role="alert">{error}</p>}
        <button className="primary-link" disabled={loading}>{loading ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}</button>
      </form>
      {mode === "login" && <p className="account-secondary-link"><Link to="/reset-password">Forgot your password?</Link></p>}
    </main>
  </SiteLayout>;
}
