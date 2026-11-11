import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { createBooking, DIRECTORY_PAGE_SIZE, getFacility, getFacilityServices, uploadBookingDocuments, type Booking, type Facility, type Service } from "../api/client";
import { useAuth } from "../components/AuthContext";
import SiteLayout from "../components/SiteLayout";

type FacilityService = Omit<Service, "facility_name" | "facility_city" | "facility_address" | "facility_phone">;

export default function FacilityDetailPage() {
  const { facilityId } = useParams();
  const id = Number(facilityId);
  const { user } = useAuth();
  const [facility, setFacility] = useState<Facility | null>(null);
  const [services, setServices] = useState<FacilityService[]>([]);
  const [servicesHaveMore, setServicesHaveMore] = useState(false);
  const [loadingMoreServices, setLoadingMoreServices] = useState(false);
  const [serviceError, setServiceError] = useState("");
  const [error, setError] = useState("");
  const [selectedServiceId, setSelectedServiceId] = useState("");
  const [appointmentAt, setAppointmentAt] = useState("");
  const [booking, setBooking] = useState<Booking | null>(null);
  const [bookingError, setBookingError] = useState("");
  const [bookingLoading, setBookingLoading] = useState(false);
  const [selectedDocuments, setSelectedDocuments] = useState<File[]>([]);
  const [documentSelectionError, setDocumentSelectionError] = useState("");
  const [documentUploadError, setDocumentUploadError] = useState("");
  const [documentsUploaded, setDocumentsUploaded] = useState(false);
  const [documentsUploading, setDocumentsUploading] = useState(false);

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
          setServicesHaveMore(serviceResults.length === DIRECTORY_PAGE_SIZE);
        }
      })
      .catch(() => { if (active) setError("Could not load this facility. It may no longer be available."); });
    return () => { active = false; };
  }, [id]);

  async function loadMoreServices() {
    setLoadingMoreServices(true);
    setServiceError("");
    try {
      const results = await getFacilityServices(id, { offset: services.length });
      setServices((current) => [...current, ...results]);
      setServicesHaveMore(results.length === DIRECTORY_PAGE_SIZE);
    } catch {
      setServiceError("Could not load more services. Please try again.");
    } finally {
      setLoadingMoreServices(false);
    }
  }

  async function submitBooking(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedServiceId || !appointmentAt || documentSelectionError) return;
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
      if (selectedDocuments.length > 0) {
        await uploadDocuments(created.id);
      }
    } catch (reason) {
      setBookingError(reason instanceof Error ? reason.message.replace(/^API error \d+: /, "") : "Unable to create your booking.");
    } finally {
      setBookingLoading(false);
    }
  }

  async function uploadDocuments(bookingId: number) {
    setDocumentsUploading(true);
    setDocumentUploadError("");
    try {
      await uploadBookingDocuments(bookingId, selectedDocuments);
      setDocumentsUploaded(true);
    } catch (reason) {
      setDocumentUploadError(reason instanceof Error
        ? reason.message.replace(/^API error \d+: /, "")
        : "The appointment was created, but the documents could not be uploaded.");
    } finally {
      setDocumentsUploading(false);
    }
  }

  function selectDocuments(files: FileList | null) {
    const selected = Array.from(files ?? []);
    setSelectedDocuments(selected);
    if (selected.length > 5) {
      setDocumentSelectionError("Choose no more than 5 documents.");
    } else if (selected.some((file) => file.size > 10 * 1024 * 1024)) {
      setDocumentSelectionError("Each document must be 10 MB or smaller.");
    } else if (selected.some((file) => !["application/pdf", "image/jpeg", "image/png"].includes(file.type))) {
      setDocumentSelectionError("Choose PDF, JPEG, or PNG files only.");
    } else {
      setDocumentSelectionError("");
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
        {facility.description && <p>{facility.description}</p>}
        <p>Local time zone: {facility.timezone}</p>
        {facility.phone && <a className="primary-link" href={`tel:${facility.phone}`}>Call {facility.phone}</a>}
        <section className="detail-services">
          <h2>Available services</h2>
          {serviceError && <p className="notice" role="alert">{serviceError}</p>}
          {services.length ? <><ul>{services.map((service) => <li key={service.id}><div><b>{service.name}</b><span>{service.category}{service.provider_name ? ` · ${service.provider_name}` : ""}</span></div><strong>₹{(service.fee_paise / 100).toFixed(2)}</strong></li>)}</ul>{servicesHaveMore && <button className="secondary-button" disabled={loadingMoreServices} onClick={loadMoreServices}>{loadingMoreServices ? "Loading…" : "Load more services"}</button>}</> : <p>No services are listed for this center yet.</p>}
        </section>
        <section className="booking-panel" id="book-appointment">
          <h2>Book an appointment</h2>
          {!user ? <p><Link to="/login">Sign in or create an account</Link> to book at this center.</p> : booking ? <div className="booking-confirmation" role="status">
            <h3>Appointment request submitted</h3>
            <p>Your request reference is <strong>#{booking.id}</strong>. The facility will review the request; a check-in code becomes available in My bookings only after it is confirmed.</p>
            <p>Payment is due at the facility. Track the request in <Link to="/bookings">My bookings</Link>.</p>
            {selectedDocuments.length > 0 && (documentsUploaded
              ? <p>{selectedDocuments.length} document{selectedDocuments.length === 1 ? "" : "s"} uploaded for this appointment.</p>
              : <div>
                <p>{documentsUploading ? "Uploading your documents…" : "Your appointment is created, but the selected documents have not uploaded yet."}</p>
                {documentUploadError && <p className="account-error" role="alert">{documentUploadError}</p>}
                {!documentsUploading && <button type="button" className="secondary-button" onClick={() => uploadDocuments(booking.id)}>Retry document upload</button>}
              </div>)}
          </div> : services.length === 0 ? <p>This center has no bookable services listed yet.</p> : <form className="account-form" onSubmit={submitBooking}>
            <label>Doctor or service<select required value={selectedServiceId} onChange={(event) => setSelectedServiceId(event.target.value)}><option value="">Choose a doctor or service</option>{services.map((service) => <option value={service.id} key={service.id}>{service.name}{service.provider_name ? ` — ${service.provider_name}` : ""} · ₹{(service.fee_paise / 100).toFixed(2)}</option>)}</select></label>
            <label>Appointment date and time<input type="datetime-local" required min={minimumAppointment} value={appointmentAt} onChange={(event) => setAppointmentAt(event.target.value)} /></label>
            <label>Previous visit reports or prescriptions (optional)
              <input type="file" accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png" multiple onChange={(event) => selectDocuments(event.currentTarget.files)} />
            </label>
            <p>Up to 5 PDF, JPEG, or PNG files; maximum 10 MB each. Documents are stored with this appointment in the database and can be accessed by you and staff assigned to this facility. Use fake/test documents only; this service is not approved for real medical records.</p>
            {documentSelectionError && <p className="account-error" role="alert">{documentSelectionError}</p>}
            <p>Pay at the facility after your appointment. Online payment is not available yet.</p>
            {bookingError && <p className="account-error" role="alert">{bookingError}</p>}
            <button className="primary-link" disabled={bookingLoading || Boolean(documentSelectionError)}>{bookingLoading ? "Submitting…" : "Request appointment"}</button>
          </form>}
        </section>
      </> : <p className="directory-meta" role="status">Loading facility…</p>}
    </main>
  </SiteLayout>;
}
