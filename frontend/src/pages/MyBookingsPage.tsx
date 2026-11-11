import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  cancelBooking,
  downloadBookingDocument,
  getBookingCheckInCode,
  getBookingDocuments,
  getMyBookings,
  type Booking,
  type BookingDocument,
} from "../api/client";
import { useAuth } from "../components/AuthContext";
import SiteLayout from "../components/SiteLayout";

export default function MyBookingsPage() {
  const { user } = useAuth();
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const [cancellingId, setCancellingId] = useState<number | null>(null);
  const [documentsByBooking, setDocumentsByBooking] = useState<Record<number, BookingDocument[]>>({});
  const [documentsLoaded, setDocumentsLoaded] = useState<Record<number, boolean>>({});
  const [documentsLoadingId, setDocumentsLoadingId] = useState<number | null>(null);
  const [downloadingDocumentId, setDownloadingDocumentId] = useState<number | null>(null);
  const [checkInCodes, setCheckInCodes] = useState<Record<number, string>>({});
  const [loadingCodeId, setLoadingCodeId] = useState<number | null>(null);

  async function loadCheckInCode(bookingId: number) {
    setActionError("");
    setLoadingCodeId(bookingId);
    try {
      const result = await getBookingCheckInCode(bookingId);
      setCheckInCodes((current) => ({ ...current, [bookingId]: result.verification_code }));
    } catch (reason) {
      setActionError(reason instanceof Error
        ? reason.message.replace(/^API error \d+: /, "")
        : "Unable to retrieve the check-in code.");
    } finally {
      setLoadingCodeId(null);
    }
  }

  async function loadDocuments(bookingId: number) {
    setActionError("");
    setDocumentsLoadingId(bookingId);
    try {
      const documents = await getBookingDocuments(bookingId);
      setDocumentsByBooking((current) => ({ ...current, [bookingId]: documents }));
      setDocumentsLoaded((current) => ({ ...current, [bookingId]: true }));
    } catch (reason) {
      setActionError(reason instanceof Error
        ? reason.message.replace(/^API error \d+: /, "")
        : "Unable to load appointment documents.");
    } finally {
      setDocumentsLoadingId(null);
    }
  }

  async function downloadDocument(bookingId: number, file: BookingDocument) {
    setActionError("");
    setDownloadingDocumentId(file.id);
    try {
      await downloadBookingDocument(bookingId, file);
    } catch (reason) {
      setActionError(reason instanceof Error
        ? reason.message.replace(/^API error \d+: /, "")
        : "Unable to download this document.");
    } finally {
      setDownloadingDocumentId(null);
    }
  }

  async function cancelAppointment(booking: Booking) {
    if (!window.confirm(`Cancel your appointment request #${booking.id}?`)) return;
    setActionError("");
    setCancellingId(booking.id);
    try {
      const updated = await cancelBooking(booking.id);
      setBookings((current) => current.map((item) => item.id === updated.id
        ? { ...item, status: updated.status }
        : item));
    } catch (reason) {
      setActionError(reason instanceof Error
        ? reason.message.replace(/^API error \d+: /, "")
        : "Unable to cancel this appointment.");
    } finally {
      setCancellingId(null);
    }
  }

  useEffect(() => {
    let active = true;
    if (!user) {
      setLoading(false);
      return () => { active = false; };
    }
    getMyBookings()
      .then((result) => { if (active) setBookings(result); })
      .catch(() => { if (active) setError("Could not load your appointments. Please sign in again and retry."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [user]);

  return <SiteLayout>
    <main className="directory-page content">
      <p className="eyebrow">YOUR APPOINTMENTS</p>
      <h1>My bookings</h1>
      {!user ? <p className="directory-intro"><Link to="/login">Sign in</Link> to see your appointment requests.</p>
        : loading ? <p className="directory-meta" role="status">Loading your bookings…</p>
          : error ? <p className="notice" role="alert">{error}</p>
            : bookings.length ? <>{actionError && <p className="account-error" role="alert">{actionError}</p>}<div className="booking-list">{bookings.map((booking) => <article className="booking-list-card" key={booking.id}>
              <div><span className="facility-type">REQUEST #{booking.id}</span><h2>{booking.service_name}</h2>{booking.provider_name && <p>{booking.provider_name}</p>}<p>{booking.facility_name}</p><p>{new Date(booking.appointment_at).toLocaleString()}</p>{booking.rejection_reason && <p>Reason: {booking.rejection_reason}</p>}</div>
              <div>
                <span className={`booking-status booking-status-${booking.status}`}>{booking.status.replaceAll("_", " ")}</span>
                {booking.status === "confirmed" && <>
                  {checkInCodes[booking.id]
                    ? <p className="booking-code" aria-label="Appointment check-in code">{checkInCodes[booking.id]}</p>
                    : <button type="button" className="secondary-button" disabled={loadingCodeId === booking.id} onClick={() => loadCheckInCode(booking.id)}>{loadingCodeId === booking.id ? "Loading…" : "View check-in code"}</button>}
                </>}
                {["requested", "confirmed"].includes(booking.status) && booking.payment_status !== "paid" && new Date(booking.appointment_at).getTime() > Date.now() && <button type="button" className="booking-cancel-button" disabled={cancellingId === booking.id} onClick={() => cancelAppointment(booking)}>{cancellingId === booking.id ? "Cancelling…" : "Cancel appointment"}</button>}
              </div>
              <section className="booking-documents">
                <h3>Reports and prescriptions</h3>
                {!documentsLoaded[booking.id] ? <button type="button" className="secondary-button" disabled={documentsLoadingId === booking.id} onClick={() => loadDocuments(booking.id)}>{documentsLoadingId === booking.id ? "Loading…" : "View documents"}</button>
                  : documentsByBooking[booking.id]?.length
                    ? <ul>{documentsByBooking[booking.id].map((file) => <li key={file.id}>
                      <span>{file.filename} · {(file.size_bytes / (1024 * 1024)).toFixed(2)} MB</span>
                      <button type="button" className="secondary-button" disabled={downloadingDocumentId === file.id} onClick={() => downloadDocument(booking.id, file)}>{downloadingDocumentId === file.id ? "Downloading…" : "Download"}</button>
                    </li>)}</ul>
                    : <p>No documents uploaded for this appointment.</p>}
              </section>
            </article>)}</div></>
              : <div className="empty-state"><b>No appointments yet</b><span>Find a service and request an appointment at a partner center.</span><Link to="/doctors">Browse doctors</Link></div>}
    </main>
  </SiteLayout>;
}
