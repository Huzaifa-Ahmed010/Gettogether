import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { cancelBooking, getMyBookings, type Booking } from "../api/client";
import { useAuth } from "../components/AuthContext";
import SiteLayout from "../components/SiteLayout";

export default function MyBookingsPage() {
  const { user } = useAuth();
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const [cancellingId, setCancellingId] = useState<number | null>(null);

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
              <div><span className="facility-type">BOOKING #{booking.id}</span><h2>{booking.service_name}</h2><p>{booking.facility_name}</p><p>{new Date(booking.appointment_at).toLocaleString()}</p></div>
              <div><span className={`booking-status booking-status-${booking.status}`}>{booking.status}</span>{booking.status === "booked" && new Date(booking.appointment_at).getTime() > Date.now() && <button type="button" className="booking-cancel-button" disabled={cancellingId === booking.id} onClick={() => cancelAppointment(booking)}>{cancellingId === booking.id ? "Cancelling…" : "Cancel appointment"}</button>}</div>
            </article>)}</div></>
              : <div className="empty-state"><b>No appointments yet</b><span>Find a service and request an appointment at a partner center.</span><Link to="/doctors">Browse doctors</Link></div>}
    </main>
  </SiteLayout>;
}
