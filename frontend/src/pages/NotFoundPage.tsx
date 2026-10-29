import { Link } from "react-router-dom";
import SiteLayout from "../components/SiteLayout";

export default function NotFoundPage() {
  return <SiteLayout>
    <main className="message-page content">
      <p className="eyebrow">404 · PAGE NOT FOUND</p>
      <h1>We couldn’t find that page</h1>
      <p>The link may be outdated, or the page may have moved.</p>
      <Link className="primary-link" to="/">Return to home</Link>
    </main>
  </SiteLayout>;
}
