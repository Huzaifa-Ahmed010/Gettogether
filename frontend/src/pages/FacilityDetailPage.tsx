import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { createBooking, getFacility, getFacilityServices, type Booking, type Facility, type Service } from "../api/client";
import { useAuth } from "../components/AuthContext";
import SiteLayout from "../components/SiteLayout";

type FacilityService = Omit<Service, "facility_name" | "facility_city" | "facility_address" | "facility_phone">;

export default function FacilityDetailPage() {
  const { facilityId } = useParams();
  const id = Number(facilityId);
  const { user } = useAuth();
  const [facility, setFacility] = useState<Facility | null>(null);
  const [services, setServices] = useState<FacilityService[]>([]);
  const [error, setError] = useState("");
  const [selectedServiceId, setSelectedServiceId] = useState("");
  const [appointmentAt, setAppointmentAt] = useState("");
  const [booking, setBooking] = useState<Booking | null>(null);
  const [bookingError, setBookingError] = useState("");
  const [bookingLoading, setBookingLoading] = useState(false);

  useEffect(() => {
    let active = true;
    if (!Number.isSafeInteger(id) || id < 1) {
      setError("This facility could not be found.");
      return () => { active = false; };
    }
    Promise.all([getFacility(id), getFacilityServices(id)])
      .then(([facilityResult, serviceResults]) => {
        if (active) {
          setFacility(facilityResult);
          setServices(serviceResults);
        }
      })
      .catch(() => { if (active) setError("Could not load this facility. It may no longer be available."); });
    return () => { active = false; };
  }, [id]);

  async function submitBooking(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedServiceId || !appointmentAt) return;
    setBookingError("");
    setBookingLoading(true);
    try {
      const created = await createBooking({
        facility_id: id,
        service_id: Number(selectedServiceId),
        appointment_at: new Date(appointmentAt).toISOString(),
        payment_method: "physical",
      });
      setBooking(created);
    } catch (reason) {
      setBookingError(reason instanceof Error ? reason.message.replace(/^API error \d+: /, "") : "Unable to create your booking.");
    } finally {
      setBookingLoading(false);
    }
  }

  const minimumAppointment = new Date(Date.now() - new Date().getTimezoneOffset() * 60_000)
    .toISOString()
    .slice(0, 16);

  return <SiteLayout>
    <main className="content facility-detail">
      {error ? <div className="message-page"><p className="notice" role="alert">{error}</p><Link to="/hospitals">Browse partner centers</Link></div> : facility ? <>
        <Link className="back-link" to="/hospitals">← Browse centers</Link>
        <p className="eyebrow">{facility.facility_type === "hospital" ? "HOSPITAL" : "DIAGNOSTIC CENTER"}</p>
        <h1>{facility.name}</h1>
        <p className="facility-address">{facility.address}, {facility.city}</p>
        {facility.phone && <a className="primary-link" href={`tel:${facility.phone}`}>Call {facility.phone}</a>}
        <section className="detail-services">
          <h2>Available services</h2>
          {services.length ? <ul>{services.map((service) => <li key={service.id}><div><b>{service.name}</b><span>{service.category}{service.provider_name ? ` · ${service.provider_name}` : ""}</span></div><strong>₹{(service.fee_paise / 100).toFixed(2)}</strong></li>)}</ul> : <p>No services are listed for this center yet.</p>}
        </section>
        <section className="booking-panel" id="book-appointment">
          <h2>Book an appointment</h2>
          {!user ? <p><Link to="/login">Sign in or create an account</Link> to book at this center.</p> : booking ? <div className="booking-confirmation" role="status">
            <h3>Appointment request submitted</h3>
            <p>Your booking reference is <strong>#{booking.id}</strong>. Show this one-time check-in code to the facility staff:</p>
            <strong className="booking-code">{booking.verification_code}</strong>
            <p>Payment is due at the facility. View the appointment in <Link to="/bookings">My bookings</Link>.</p>
          </div> : services.length === 0 ? <p>This center has no bookable services listed yet.</p> : <form className="account-form" onSubmit={submitBooking}>
            <label>Service<select required value={selectedServiceId} onChange={(event) => setSelectedServiceId(event.target.value)}><option value="">Choose a service</option>{services.map((service) => <option value={service.id} key={service.id}>{service.name} · ₹{(service.fee_paise / 100).toFixed(2)}</option>)}</select></label>
            <label>Appointment date and time<input type="datetime-local" required min={minimumAppointment} value={appointmentAt} onChange={(event) => setAppointmentAt(event.target.value)} /></label>
            <p>Pay at the facility after your appointment. Online payment is not available yet.</p>
            {bookingError && <p className="account-error" role="alert">{bookingError}</p>}
            <button className="primary-link" disabled={bookingLoading}>{bookingLoading ? "Submitting…" : "Request appointment"}</button>
          </form>}
        </section>
      </> : <p className="directory-meta" role="status">Loading facility…</p>}
    </main>
  </SiteLayout>;
}
