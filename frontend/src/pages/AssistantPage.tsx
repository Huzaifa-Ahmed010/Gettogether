import { type FormEvent, useState } from "react";
import { ArrowRight, HeartPulse } from "lucide-react";
import { sendAssistantMessage } from "../api/client";
import SiteLayout from "../components/SiteLayout";

export default function AssistantPage() {
  const [message, setMessage] = useState("");
  const [reply, setReply] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedMessage = message.trim();
    if (!trimmedMessage || loading) return;
    setError("");
    setReply("");
    setLoading(true);
    try {
      const response = await sendAssistantMessage(trimmedMessage);
      setReply(response.reply);
      setMessage("");
    } catch {
      setError("The assistant is unavailable right now. Please try again later.");
    } finally {
      setLoading(false);
    }
  }

  return <SiteLayout>
    <main className="assistant-page content">
      <div className="assistant-title"><span className="assistant-icon"><HeartPulse size={29} /></span><div><p className="eyebrow">HERE TO HELP</p><h1>GetTogether care navigator</h1></div></div>
      <p className="directory-intro">Ask about doctors, tests, or care centers in our directory. GetTogether uses listed services to help you navigate; it does not diagnose or recommend treatment.</p>
      <form className="assistant-form" onSubmit={submit}>
        <label htmlFor="assistant-message">Your question</label>
        <textarea id="assistant-message" value={message} maxLength={2000} onChange={(event) => setMessage(event.target.value)} placeholder="What kind of care are you looking for?" required />
        <button className="assistant-action" disabled={loading || !message.trim()}>{loading ? "Sending…" : "Send message"} <ArrowRight size={17} /></button>
      </form>
      {error && <p className="notice" role="alert">{error}</p>}
      {reply && <section className="assistant-reply" aria-live="polite"><h2>Assistant reply</h2><p>{reply}</p></section>}
    </main>
  </SiteLayout>;
}
