import { type FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { loginAccount, registerAccount, resendEmailVerification, verifyEmailAddress } from "../api/client";
import { useAuth } from "../components/AuthContext";
import SiteLayout from "../components/SiteLayout";

export default function LoginPage() {
  const navigate = useNavigate();
  const { user, saveSession, signOut } = useAuth();
  const [mode, setMode] = useState<"login" | "register" | "verify">("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [developmentOtp, setDevelopmentOtp] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      if (mode === "register") {
        const pending = await registerAccount({ name, email, password });
        setEmail(pending.email);
        setDevelopmentOtp(pending.development_otp ?? "");
        setNotice(pending.message);
        setMode("verify");
        return;
      }
      const response = mode === "verify"
        ? await verifyEmailAddress({ email, code })
        : await loginAccount({ email, password });
      saveSession(response);
      navigate("/");
    } catch (reason) {
      const message = reason instanceof Error ? reason.message.replace(/^API error \d+: /, "") : "Unable to access your account.";
      setError(message);
      if (mode === "login" && message.toLowerCase().includes("email not verified")) {
        setMode("verify");
        setNotice("Enter the verification code sent to your email address.");
      }
    } finally {
      setLoading(false);
    }
  }

  async function resendCode() {
    setError("");
    setLoading(true);
    try {
      const response = await resendEmailVerification(email);
      setNotice(response.message);
      setDevelopmentOtp(response.development_otp ?? "");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message.replace(/^API error \d+: /, "") : "Unable to resend the verification email.");
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
      <h1>{mode === "login" ? "Welcome back" : mode === "register" ? "Create your account" : "Verify your email"}</h1>
      <p className="directory-intro">Sign in to your GetTogether account or create one to get started.</p>
      {mode !== "verify" && <div className="account-tabs" role="tablist" aria-label="Account access">
        <button type="button" role="tab" aria-selected={mode === "login"} onClick={() => { setMode("login"); setError(""); }}>Sign in</button>
        <button type="button" role="tab" aria-selected={mode === "register"} onClick={() => { setMode("register"); setError(""); }}>Create account</button>
      </div>}
      <form className="account-form" onSubmit={submit}>
        {mode === "register" && <label>Full name<input autoComplete="name" required minLength={2} maxLength={120} value={name} onChange={(event) => setName(event.target.value)} /></label>}
        <label>Email address<input type="email" autoComplete="email" required maxLength={254} readOnly={mode === "verify"} value={email} onChange={(event) => setEmail(event.target.value)} /></label>
        {mode === "verify" ? <label>6-digit email code<input inputMode="numeric" autoComplete="one-time-code" required pattern="[0-9]{6}" minLength={6} maxLength={6} value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))} /></label> : <label>Password<input type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} required minLength={mode === "register" ? 12 : 1} maxLength={128} value={password} onChange={(event) => setPassword(event.target.value)} />{mode === "register" && <small>Use at least 12 characters.</small>}</label>}
        {notice && <p className="account-notice" role="status">{notice}{developmentOtp && <strong> Local development verification code: {developmentOtp}</strong>}</p>}
        {error && <p className="account-error" role="alert">{error}</p>}
        <button className="primary-link" disabled={loading}>{loading ? "Please wait…" : mode === "login" ? "Sign in" : mode === "register" ? "Create account" : "Verify email"}</button>
      </form>
      {mode === "login" && <p className="account-secondary-link"><Link to="/reset-password">Forgot your password?</Link></p>}
      {mode === "verify" && <div className="account-secondary-actions"><button type="button" onClick={resendCode} disabled={loading}>Resend code</button><button type="button" onClick={() => { setMode("login"); setError(""); setNotice(""); }}>Back to sign in</button></div>}
    </main>
  </SiteLayout>;
}
