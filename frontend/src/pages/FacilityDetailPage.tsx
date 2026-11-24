import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ClipboardPlus, MapPin, Star, Stethoscope } from "lucide-react";
import { createBooking, DIRECTORY_PAGE_SIZE, getFacility, getFacilityImageUrl, getFacilityReviews, getFacilityServices, getServiceImageUrl, uploadBookingDocuments, type Booking, type Facility, type FacilityReviewSummary, type Service } from "../api/client";
import { useAuth } from "../components/AuthContext";
import SiteLayout from "../components/SiteLayout";

type FacilityService = Omit<Service, "facility_name" | "facility_city" | "facility_address" | "facility_phone">;
type DetailTab = "services" | "overview" | "ratings";

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
  const [detailTab, setDetailTab] = useState<DetailTab>("services");
  const [reviewSummary, setReviewSummary] = useState<FacilityReviewSummary | null>(null);
  const [reviewsLoading, setReviewsLoading] = useState(false);
  const [reviewsError, setReviewsError] = useState("");
  const [facilityImageUnavailable, setFacilityImageUnavailable] = useState(false);

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

  useEffect(() => {
    if (!facility || detailTab !== "ratings") return;
    let active = true;
    setReviewsLoading(true);
    setReviewsError("");
    getFacilityReviews(facility.id)
      .then((result) => { if (active) setReviewSummary(result); })
      .catch((reason: unknown) => {
        if (active) {
          setReviewsError(reason instanceof Error
            ? reason.message.replace(/^API error \d+: /, "")
            : "Could not load facility ratings.");
        }
      })
      .finally(() => { if (active) setReviewsLoading(false); });
    return () => { active = false; };
  }, [detailTab, facility]);

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
  const directionsUrl = facility
    ? facility.latitude !== null && facility.longitude !== null
      ? `https://www.google.com/maps/dir/?api=1&destination=${facility.latitude},${facility.longitude}`
      : `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${facility.name}, ${facility.address}, ${facility.city}`)}`
    : "";

  return <SiteLayout>
    <main className="content facility-detail">
      {error ? <div className="message-page"><p className="notice" role="alert">{error}</p><Link to="/hospitals">Browse partner centers</Link></div> : facility ? <>
        <Link className="back-link" to="/hospitals">← Browse centers</Link>
        <section className="facility-detail-hero">
          <div className="facility-detail-heading">
            <p className="eyebrow">{facility.facility_type === "hospital" ? "HOSPITAL" : "DIAGNOSTIC CENTER"}</p>
            <h1>{facility.name}</h1>
            <p className="facility-address"><MapPin size={17} />{facility.address}, {facility.city}</p>
            <div className="facility-detail-actions">
              {facility.phone && <a className="primary-link" href={`tel:${facility.phone}`}>Call {facility.phone}</a>}
              <a className="secondary-button" href={directionsUrl} target="_blank" rel="noopener noreferrer"><MapPin size={16} /> Get directions</a>
            </div>
          </div>
          <div className="facility-detail-photo">
            {facilityImageUnavailable
              ? <div className="facility-photo-placeholder"><ClipboardPlus size={52} /><span>{facility.facility_type === "hospital" ? "Hospital" : "Diagnostic center"}</span></div>
              : <img src={getFacilityImageUrl(facility.id)} alt={`${facility.name}`} onError={() => setFacilityImageUnavailable(true)} />}
          </div>
        </section>

        <div className="facility-detail-tabs" role="tablist" aria-label="Facility information">
          <button type="button" role="tab" aria-selected={detailTab === "services"} onClick={() => setDetailTab("services")}>Available services</button>
          <button type="button" role="tab" aria-selected={detailTab === "overview"} onClick={() => setDetailTab("overview")}>Overview</button>
          <button type="button" role="tab" aria-selected={detailTab === "ratings"} onClick={() => setDetailTab("ratings")}>Ratings</button>
        </div>

        {detailTab === "services" && <>
          <section className="detail-services">
            <div className="section-heading"><h2>Available services</h2><span>{services.length}{servicesHaveMore ? "+" : ""} listed</span></div>
            {serviceError && <p className="notice" role="alert">{serviceError}</p>}
            {services.length ? <><ul>{services.map((service) => <li key={service.id}>
              <div className="service-list-image">
                <ServiceImage facilityId={facility.id} service={service} />
              </div>
              <div className="service-list-copy"><b>{service.name}</b><span>{service.category}{service.provider_name ? ` · ${service.provider_name}` : ""}</span></div>
              <strong>₹{(service.fee_paise / 100).toFixed(2)}</strong>
            </li>)}</ul>{servicesHaveMore && <button className="secondary-button" disabled={loadingMoreServices} onClick={loadMoreServices}>{loadingMoreServices ? "Loading…" : "Load more services"}</button>}</> : <p>No services are listed for this center yet.</p>}
          </section>
          <section className="booking-panel" id="book-appointment">
            <h2>Book an appointment</h2>
            {!user ? <p><Link to="/login">Sign in or create an account</Link> to book at this center.</p> : user.role !== "patient" ? <p>Appointment requests are available to patient accounts only. Use your management workspace to manage this facility or the platform.</p> : booking ? <div className="booking-confirmation" role="status">
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
        </>}

        {detailTab === "overview" && <section className="facility-overview-panel">
          <h2>About {facility.name}</h2>
          <p>{facility.description || "Facility information has not been added yet."}</p>
          <dl>
            <div><dt>Address</dt><dd>{facility.address}, {facility.city}</dd></div>
            {facility.phone && <div><dt>Phone</dt><dd><a href={`tel:${facility.phone}`}>{facility.phone}</a></dd></div>}
            <div><dt>Local time zone</dt><dd>{facility.timezone}</dd></div>
            <div><dt>Facility type</dt><dd>{facility.facility_type === "hospital" ? "Hospital" : "Diagnostic center"}</dd></div>
          </dl>
          <a className="secondary-button" href={directionsUrl} target="_blank" rel="noopener noreferrer"><MapPin size={16} /> Get directions</a>
        </section>}

        {detailTab === "ratings" && <section className="facility-ratings-panel">
          <div className="section-heading"><div><h2>Patient ratings</h2><p>Ratings are from patients with a completed appointment. Patient identities are not shown.</p></div></div>
          {reviewsLoading && <p role="status">Loading ratings…</p>}
          {reviewsError && <p className="notice" role="alert">{reviewsError}</p>}
          {!reviewsLoading && !reviewsError && reviewSummary && <>
            <div className="rating-summary">
              <strong>{reviewSummary.average_rating === null ? "—" : reviewSummary.average_rating.toFixed(1)}</strong>
              <div><Stars rating={reviewSummary.average_rating ?? 0} /><span>{reviewSummary.ratings_count} {reviewSummary.ratings_count === 1 ? "verified rating" : "verified ratings"}</span></div>
            </div>
            {reviewSummary.reviews.length ? <div className="facility-review-list">
              {reviewSummary.reviews.map((review) => <article key={review.id}>
                <Stars rating={review.rating} />
                <p>{review.comment || "Patient left a rating without a written review."}</p>
                <span>Verified appointment · {new Date(review.created_at).toLocaleDateString()}</span>
              </article>)}
            </div> : <p className="admin-empty">No ratings yet. Patients can leave one after their appointment is completed.</p>}
          </>}
        </section>}
      </> : <p className="directory-meta" role="status">Loading facility…</p>}
    </main>
  </SiteLayout>;
}

function Stars({ rating }: { rating: number }) {
  return <span className="rating-stars" aria-label={`${rating} out of 5 stars`}>
    {Array.from({ length: 5 }, (_, index) => <Star key={index} size={16} fill={index < Math.round(rating) ? "currentColor" : "none"} />)}
  </span>;
}

function ServiceImage({ facilityId, service }: { facilityId: number; service: FacilityService }) {
  const [imageUnavailable, setImageUnavailable] = useState(false);
  return imageUnavailable
    ? service.service_type === "doctor" ? <Stethoscope size={24} /> : <ClipboardPlus size={24} />
    : <img
      src={getServiceImageUrl(facilityId, service.id)}
      alt={service.provider_name ? `${service.provider_name} profile` : `${service.name} image`}
      onError={() => setImageUnavailable(true)}
    />;
}
