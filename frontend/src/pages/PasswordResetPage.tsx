import { type FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { completePasswordReset, requestPasswordReset } from "../api/client";
import SiteLayout from "../components/SiteLayout";

export default function PasswordResetPage() {
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [developmentOtp, setDevelopmentOtp] = useState("");
  const [stage, setStage] = useState<"request" | "reset" | "complete">("request");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      if (stage === "request") {
        const result = await requestPasswordReset(email);
        setNotice(result.message);
        setDevelopmentOtp(result.development_otp ?? "");
        setStage("reset");
      } else {
        const result = await completePasswordReset({
          email,
          code,
          new_password: password,
        });
        setNotice(result.message);
        setDevelopmentOtp("");
        setStage("complete");
      }
    } catch (reason) {
      setError(reason instanceof Error
        ? reason.message.replace(/^API error \d+: /, "")
        : "Unable to reset your password. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  async function resendCode() {
    setError("");
    setLoading(true);
    try {
      const result = await requestPasswordReset(email);
      setNotice(result.message);
      setDevelopmentOtp(result.development_otp ?? "");
    } catch (reason) {
      setError(reason instanceof Error
        ? reason.message.replace(/^API error \d+: /, "")
        : "Unable to request another reset code.");
    } finally {
      setLoading(false);
    }
  }

  return <SiteLayout>
    <main className="account-page content">
      <p className="eyebrow">ACCOUNT RECOVERY</p>
      <h1>{stage === "complete" ? "Password updated" : "Reset your password"}</h1>
      {stage === "complete" ? <>
        <p className="account-notice" role="status">{notice}</p>
        <p><Link to="/login">Return to sign in</Link></p>
      </> : <>
        <p className="directory-intro">We will send a time-limited code to the email address on your account.</p>
        <form className="account-form" onSubmit={submit}>
          <label>Email address<input type="email" autoComplete="email" required maxLength={254} readOnly={stage === "reset"} value={email} onChange={(event) => setEmail(event.target.value)} /></label>
          {stage === "reset" && <>
            <label>6-digit reset code<input inputMode="numeric" autoComplete="one-time-code" required pattern="[0-9]{6}" minLength={6} maxLength={6} value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))} /></label>
            <label>New password<input type="password" autoComplete="new-password" required minLength={12} maxLength={128} value={password} onChange={(event) => setPassword(event.target.value)} /><small>Use at least 12 characters.</small></label>
          </>}
          {notice && <p className="account-notice" role="status">{notice}{developmentOtp && <strong> Local development reset code: {developmentOtp}</strong>}</p>}
          {error && <p className="account-error" role="alert">{error}</p>}
          <button className="primary-link" disabled={loading}>{loading ? "Please wait…" : stage === "request" ? "Send reset code" : "Update password"}</button>
        </form>
        {stage === "reset" && <div className="account-secondary-actions"><button type="button" onClick={resendCode} disabled={loading}>Resend code</button></div>}
        <p className="account-secondary-link"><Link to="/login">Back to sign in</Link></p>
      </>}
    </main>
  </SiteLayout>;
}
