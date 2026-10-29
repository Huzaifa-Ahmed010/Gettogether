import { type FormEvent, useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../components/AuthContext";
import SiteLayout from "../components/SiteLayout";
import {
  cancelManagedBooking,
  createFacility,
  createFacilityService,
  getAdminDashboard,
  getManagedBookings,
  getManagedFacilities,
  getManagedServices,
  getManagedUsers,
  updateManagedFacility,
  updateManagedService,
  updateManagedUser,
  verifyBooking,
  type AdminBooking,
  type AdminDashboard,
  type AdminUser,
  type Facility,
  type ManagedService,
} from "../api/client";

type AdminTab = "directory" | "bookings" | "accounts";

function errorText(error: unknown) {
  return error instanceof Error ? error.message : "The request could not be completed.";
}

function formatAppointment(value: string) {
  return new Date(value).toLocaleString();
}

export default function AdminPage() {
  const { user } = useAuth();
  const isPlatformAdmin = user?.role === "platform_admin";
  const canManage = isPlatformAdmin || user?.role === "facility_staff";
  const [tab, setTab] = useState<AdminTab>("directory");
  const [dashboard, setDashboard] = useState<AdminDashboard | null>(null);
  const [facilities, setFacilities] = useState<Facility[]>([]);
  const [selectedFacilityId, setSelectedFacilityId] = useState<number | null>(null);
  const [services, setServices] = useState<ManagedService[]>([]);
  const [bookings, setBookings] = useState<AdminBooking[]>([]);
  const [accounts, setAccounts] = useState<AdminUser[]>([]);
  const [bookingStatus, setBookingStatus] = useState("");
  const [bookingFacilityFilter, setBookingFacilityFilter] = useState("");
  const [codes, setCodes] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const selectedFacility = facilities.find((facility) => facility.id === selectedFacilityId) ?? null;

  async function loadDashboard() {
    setDashboard(await getAdminDashboard());
  }

  async function loadDirectory() {
    const [stats, items] = await Promise.all([getAdminDashboard(), getManagedFacilities()]);
    setDashboard(stats);
    setFacilities(items);
    setSelectedFacilityId((current) =>
      items.some((facility) => facility.id === current) ? current : (items[0]?.id ?? null)
    );
  }

  async function loadBookings() {
    const result = await getManagedBookings({
      status: bookingStatus || undefined,
      facility_id: isPlatformAdmin && bookingFacilityFilter
        ? Number(bookingFacilityFilter)
        : undefined,
    });
    setBookings(result);
  }

  async function loadAccounts() {
    if (!isPlatformAdmin) return;
    setAccounts(await getManagedUsers());
  }

  useEffect(() => {
    if (!canManage) return;
    let active = true;
    setLoading(true);
    Promise.all([getAdminDashboard(), getManagedFacilities()])
      .then(([stats, items]) => {
        if (!active) return;
        setDashboard(stats);
        setFacilities(items);
        setSelectedFacilityId((current) =>
          items.some((facility) => facility.id === current) ? current : (items[0]?.id ?? null)
        );
      })
      .catch((reason: unknown) => {
        if (active) setError(errorText(reason));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [canManage]);

  useEffect(() => {
    if (!canManage || selectedFacilityId === null) {
      setServices([]);
      return;
    }
    let active = true;
    getManagedServices(selectedFacilityId)
      .then((items) => {
        if (active) setServices(items);
      })
      .catch((reason: unknown) => {
        if (active) setError(errorText(reason));
      });
    return () => {
      active = false;
    };
  }, [canManage, selectedFacilityId]);

  useEffect(() => {
    if (!canManage || tab !== "bookings") return;
    let active = true;
    getManagedBookings({
      status: bookingStatus || undefined,
      facility_id: isPlatformAdmin && bookingFacilityFilter
        ? Number(bookingFacilityFilter)
        : undefined,
    })
      .then((items) => {
        if (active) setBookings(items);
      })
      .catch((reason: unknown) => {
        if (active) setError(errorText(reason));
      });
    return () => {
      active = false;
    };
  }, [bookingFacilityFilter, bookingStatus, canManage, isPlatformAdmin, tab]);

  useEffect(() => {
    if (!canManage || !isPlatformAdmin || tab !== "accounts") return;
    let active = true;
    getManagedUsers()
      .then((items) => {
        if (active) setAccounts(items);
      })
      .catch((reason: unknown) => {
        if (active) setError(errorText(reason));
      });
    return () => {
      active = false;
    };
  }, [canManage, isPlatformAdmin, tab]);

  async function submitNewFacility(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const created = await createFacility({
        name: String(form.get("name")),
        facility_type: String(form.get("facility_type")) as Facility["facility_type"],
        address: String(form.get("address")),
        city: String(form.get("city")),
        phone: String(form.get("phone") ?? ""),
      });
      setNotice("Facility added.");
      await loadDirectory();
      setSelectedFacilityId(created.id);
      formElement.reset();
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setSaving(false);
    }
  }

  async function submitFacilityUpdate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedFacility) return;
    const form = new FormData(event.currentTarget);
    const payload: Partial<Omit<Facility, "id">> = {
      name: String(form.get("name")),
      facility_type: String(form.get("facility_type")) as Facility["facility_type"],
      address: String(form.get("address")),
      city: String(form.get("city")),
      phone: String(form.get("phone") ?? ""),
    };
    if (isPlatformAdmin) payload.is_active = form.get("is_active") === "on";
    setSaving(true);
    setError("");
    setNotice("");
    try {
      await updateManagedFacility(selectedFacility.id, payload);
      setNotice("Facility details saved.");
      await loadDirectory();
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setSaving(false);
    }
  }

  async function submitService(event: FormEvent<HTMLFormElement>, existing?: ManagedService) {
    event.preventDefault();
    if (!selectedFacility) return;
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const payload = {
      name: String(form.get("name")),
      category: String(form.get("category")),
      service_type: String(form.get("service_type")) as ManagedService["service_type"],
      provider_name: String(form.get("provider_name") ?? ""),
      fee_paise: Math.round(Number(form.get("fee")) * 100),
    };
    setSaving(true);
    setError("");
    setNotice("");
    try {
      if (existing) {
        await updateManagedService(selectedFacility.id, existing.id, payload);
        setNotice("Service details saved.");
      } else {
        await createFacilityService(selectedFacility.id, payload);
        setNotice("Service added.");
        formElement.reset();
      }
      setServices(await getManagedServices(selectedFacility.id));
      await loadDashboard();
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setSaving(false);
    }
  }

  async function toggleFacility(facility: Facility) {
    const action = facility.is_active ? "deactivate" : "activate";
    if (!window.confirm(`${action[0].toUpperCase()}${action.slice(1)} ${facility.name}?`)) return;
    setSaving(true);
    setError("");
    setNotice("");
    try {
      await updateManagedFacility(facility.id, { is_active: !facility.is_active });
      setNotice(facility.is_active ? "Facility deactivated." : "Facility activated.");
      await loadDirectory();
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setSaving(false);
    }
  }

  async function toggleService(service: ManagedService) {
    if (!selectedFacility) return;
    setSaving(true);
    setError("");
    setNotice("");
    try {
      await updateManagedService(selectedFacility.id, service.id, { is_active: !service.is_active });
      setNotice(service.is_active ? "Service deactivated." : "Service activated.");
      setServices(await getManagedServices(selectedFacility.id));
      await loadDashboard();
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setSaving(false);
    }
  }

  async function cancelBooking(booking: AdminBooking) {
    if (!window.confirm(`Cancel the booking for ${booking.patient_name}?`)) return;
    setSaving(true);
    setError("");
    setNotice("");
    try {
      await cancelManagedBooking(booking.id);
      setNotice("Booking cancelled.");
      await loadBookings();
      await loadDashboard();
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setSaving(false);
    }
  }

  async function submitVerification(event: FormEvent<HTMLFormElement>, booking: AdminBooking) {
    event.preventDefault();
    const code = codes[booking.id] ?? "";
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const result = await verifyBooking(code);
      if (result.valid) {
        setNotice(result.message);
        setCodes((current) => ({ ...current, [booking.id]: "" }));
        await loadBookings();
        await loadDashboard();
      } else {
        setError(result.message);
      }
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setSaving(false);
    }
  }

  async function submitAccountUpdate(event: FormEvent<HTMLFormElement>, account: AdminUser) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const role = String(form.get("role")) as "patient" | "facility_staff";
    const payload: { role: "patient" | "facility_staff"; facility_id?: number } = { role };
    if (role === "facility_staff") {
      const facilityId = Number(form.get("facility_id"));
      if (!Number.isInteger(facilityId) || facilityId < 1) {
        setError("Choose a facility for this staff account.");
        return;
      }
      payload.facility_id = facilityId;
    }
    setSaving(true);
    setError("");
    setNotice("");
    try {
      await updateManagedUser(account.id, payload);
      setNotice("Account access updated; existing sessions were signed out.");
      await loadAccounts();
      await loadDashboard();
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setSaving(false);
    }
  }

  async function toggleAccount(account: AdminUser) {
    const action = account.is_active ? "deactivate" : "activate";
    if (!window.confirm(`${action[0].toUpperCase()}${action.slice(1)} ${account.name}'s account?`)) return;
    setSaving(true);
    setError("");
    setNotice("");
    try {
      await updateManagedUser(account.id, { is_active: !account.is_active });
      setNotice(account.is_active ? "Account deactivated." : "Account activated.");
      await loadAccounts();
      await loadDashboard();
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setSaving(false);
    }
  }

  if (!user) return <Navigate to="/login" replace />;
  if (!canManage) {
    return <SiteLayout><main className="admin-page content"><h1>Admin access required</h1><p>Your account does not have permission to manage GetTogether.</p></main></SiteLayout>;
  }

  return <SiteLayout>
    <main className="admin-page content">
      <p className="eyebrow">GETTOGETHER MANAGEMENT</p>
      <h1>{isPlatformAdmin ? "Admin panel" : "Facility workspace"}</h1>
      <p className="directory-intro">Manage service listings and bookings using your assigned access.</p>
      <p className="admin-demo-notice">Demo only: use fake records. Do not enter real patient information.</p>
      {error && <p className="notice" role="alert">{error}</p>}
      {notice && <p className="admin-success" role="status">{notice}</p>}
      {loading && <p role="status">Loading management data…</p>}

      {dashboard && <div className="admin-stats">
        <article><span>Active facilities</span><strong>{dashboard.facilities}</strong></article>
        <article><span>Active services</span><strong>{dashboard.services}</strong></article>
        <article><span>Bookings</span><strong>{dashboard.bookings}</strong></article>
        {isPlatformAdmin && <article><span>Accounts</span><strong>{dashboard.users ?? 0}</strong></article>}
      </div>}

      <div className="admin-tabs" role="tablist" aria-label="Admin sections">
        <button type="button" role="tab" aria-selected={tab === "directory"} onClick={() => setTab("directory")}>Facilities & services</button>
        <button type="button" role="tab" aria-selected={tab === "bookings"} onClick={() => setTab("bookings")}>Bookings</button>
        {isPlatformAdmin && <button type="button" role="tab" aria-selected={tab === "accounts"} onClick={() => setTab("accounts")}>User accounts</button>}
      </div>

      {tab === "directory" && <section className="admin-section">
        {isPlatformAdmin && <form className="admin-form" onSubmit={submitNewFacility}>
          <h2>Add a facility</h2>
          <FacilityFields />
          <button className="primary-link" disabled={saving}>{saving ? "Saving…" : "Add facility"}</button>
        </form>}

        <section className="admin-panel">
          <div className="admin-panel-heading">
            <div><p className="eyebrow">DIRECTORY</p><h2>Manage facilities</h2></div>
            {isPlatformAdmin && facilities.length > 0 && <label className="admin-select-label">Choose facility
              <select value={selectedFacilityId ?? ""} onChange={(event) => setSelectedFacilityId(Number(event.target.value) || null)}>
                {facilities.map((facility) => <option key={facility.id} value={facility.id}>{facility.name}{facility.is_active ? "" : " (inactive)"}</option>)}
              </select>
            </label>}
          </div>
          {!selectedFacility && <p className="admin-empty">No facility is available to manage yet.</p>}
          {selectedFacility && <>
            <form key={selectedFacility.id} className="admin-form admin-form-inline" onSubmit={submitFacilityUpdate}>
              <h3>Facility details</h3>
              <FacilityFields facility={selectedFacility} />
              {isPlatformAdmin && <label className="admin-checkbox"><input type="checkbox" name="is_active" defaultChecked={selectedFacility.is_active} /> Listed publicly</label>}
              <button className="primary-link" disabled={saving}>{saving ? "Saving…" : "Save facility"}</button>
            </form>

            <div className="admin-list-heading"><h3>Services</h3><span>{services.length} total</span></div>
            {services.length === 0 && <p className="admin-empty">No services have been added to this facility yet.</p>}
            <div className="admin-item-list">
              {services.map((service) => <article className="admin-item" key={service.id}>
                <form className="admin-form admin-item-form" onSubmit={(event) => submitService(event, service)}>
                  <div className="admin-item-heading"><div><h4>{service.name}</h4><span className={service.is_active ? "admin-status active" : "admin-status"}>{service.is_active ? "Active" : "Inactive"}</span></div></div>
                  <ServiceFields service={service} />
                  <div className="admin-actions">
                    <button className="primary-link" disabled={saving}>{saving ? "Saving…" : "Save service"}</button>
                    <button type="button" className="secondary-button" disabled={saving} onClick={() => toggleService(service)}>{service.is_active ? "Deactivate" : "Activate"}</button>
                  </div>
                </form>
              </article>)}
            </div>

            {selectedFacility.is_active && <form className="admin-form admin-add-service" onSubmit={(event) => submitService(event)}>
              <h3>Add a service</h3>
              <ServiceFields />
              <button className="primary-link" disabled={saving}>{saving ? "Saving…" : "Add service"}</button>
            </form>}
          </>}
        </section>

        {isPlatformAdmin && <section className="admin-panel">
          <div className="admin-panel-heading"><h2>All facilities</h2></div>
          <div className="admin-item-list">
            {facilities.map((facility) => <article className="admin-item admin-facility-row" key={facility.id}>
              <div><h3>{facility.name}</h3><p>{facility.city} · {facility.facility_type}</p><span className={facility.is_active ? "admin-status active" : "admin-status"}>{facility.is_active ? "Listed publicly" : "Not listed"}</span></div>
              <div className="admin-actions"><button type="button" className="secondary-button" onClick={() => setSelectedFacilityId(facility.id)}>Edit</button><button type="button" className="secondary-button" disabled={saving} onClick={() => toggleFacility(facility)}>{facility.is_active ? "Deactivate" : "Activate"}</button></div>
            </article>)}
          </div>
        </section>}
      </section>}

      {tab === "bookings" && <section className="admin-panel">
        <div className="admin-panel-heading"><div><p className="eyebrow">APPOINTMENTS</p><h2>Bookings</h2></div>
          <div className="admin-booking-filters">
            {isPlatformAdmin && <label className="admin-select-label">Facility
              <select value={bookingFacilityFilter} onChange={(event) => setBookingFacilityFilter(event.target.value)}>
                <option value="">All facilities</option>{facilities.map((facility) => <option key={facility.id} value={facility.id}>{facility.name}</option>)}
              </select>
            </label>}
            <label className="admin-select-label">Status
              <select value={bookingStatus} onChange={(event) => setBookingStatus(event.target.value)}>
                <option value="">All statuses</option><option value="booked">Booked</option><option value="verified">Verified</option><option value="cancelled">Cancelled</option>
              </select>
            </label>
          </div>
        </div>
        {bookings.length === 0 && <p className="admin-empty">No bookings match this filter.</p>}
        <div className="admin-item-list">
          {bookings.map((booking) => <article className="admin-item admin-booking" key={booking.id}>
            <div className="admin-item-heading"><div><h3>{booking.service_name}</h3><span className={`admin-status ${booking.status}`}>{booking.status}</span></div><b>{booking.facility_name}</b></div>
            <p>{booking.patient_name} · {booking.patient_email_masked}</p>
            <p>{formatAppointment(booking.appointment_at)}</p>
            <p>Payment: {booking.payment_status} · {booking.payment_method === "physical" ? "at facility" : booking.payment_method}</p>
            {booking.status === "booked" && <div className="admin-actions admin-booking-actions">
              <form className="admin-verify-form" onSubmit={(event) => submitVerification(event, booking)}>
                <label htmlFor={`booking-code-${booking.id}`}>6-digit check-in code</label>
                <input id={`booking-code-${booking.id}`} value={codes[booking.id] ?? ""} inputMode="numeric" pattern="[0-9]{6}" maxLength={6} required onChange={(event) => setCodes((current) => ({ ...current, [booking.id]: event.target.value.replace(/\D/g, "").slice(0, 6) }))} />
                <button className="secondary-button" disabled={saving}>Verify booking</button>
              </form>
              <button type="button" className="danger-button" disabled={saving || new Date(booking.appointment_at).getTime() <= Date.now()} onClick={() => cancelBooking(booking)}>Cancel booking</button>
            </div>}
          </article>)}
        </div>
      </section>}

      {tab === "accounts" && isPlatformAdmin && <section className="admin-panel">
        <div className="admin-panel-heading"><div><p className="eyebrow">ACCESS CONTROL</p><h2>User accounts</h2></div></div>
        <p className="admin-guidance">Only verified accounts can be assigned as facility staff. Dashboard changes sign the user out. Platform administrator roles are operator-managed and cannot be changed here.</p>
        {accounts.length === 0 && <p className="admin-empty">No accounts are registered yet.</p>}
        <div className="admin-item-list">
          {accounts.map((account) => <article className="admin-item admin-account" key={account.id}>
            <div className="admin-item-heading"><div><h3>{account.name}</h3><p>{account.email}</p></div><span className={account.is_active ? "admin-status active" : "admin-status"}>{account.is_active ? "Active" : "Inactive"}</span></div>
            <p>Current access: {account.role.replace("_", " ")}{account.facility_name ? ` · ${account.facility_name}` : ""} · {account.email_verified ? "Verified" : "Not verified"}</p>
            {account.role !== "platform_admin" && <form className="admin-account-form" onSubmit={(event) => submitAccountUpdate(event, account)}>
              <label>Role<select name="role" defaultValue={account.role === "facility_staff" ? "facility_staff" : "patient"} disabled={!account.email_verified}>
                <option value="patient">Patient</option><option value="facility_staff">Facility staff</option>
              </select></label>
              <label>Assigned facility<select name="facility_id" defaultValue={account.facility_id ?? ""} disabled={!account.email_verified}>
                <option value="">Choose facility</option>{facilities.filter((facility) => facility.is_active).map((facility) => <option key={facility.id} value={facility.id}>{facility.name}</option>)}
              </select></label>
              <div className="admin-actions"><button className="primary-link" disabled={saving || !account.email_verified}>{saving ? "Saving…" : "Save access"}</button><button type="button" className="secondary-button" disabled={saving} onClick={() => toggleAccount(account)}>{account.is_active ? "Deactivate account" : "Activate account"}</button></div>
            </form>}
          </article>)}
        </div>
      </section>}
    </main>
  </SiteLayout>;
}

function FacilityFields({ facility }: { facility?: Facility }) {
  return <>
    <label>Facility name<input name="name" minLength={2} maxLength={180} defaultValue={facility?.name ?? ""} required /></label>
    <label>Facility type<select name="facility_type" defaultValue={facility?.facility_type ?? "hospital"}><option value="hospital">Hospital</option><option value="diagnostic">Diagnostic center</option></select></label>
    <label>Address<input name="address" minLength={5} defaultValue={facility?.address ?? ""} required /></label>
    <label>City<input name="city" minLength={2} maxLength={100} defaultValue={facility?.city ?? ""} required /></label>
    <label>Phone<input name="phone" maxLength={30} defaultValue={facility?.phone ?? ""} /></label>
  </>;
}

function ServiceFields({ service }: { service?: ManagedService }) {
  return <>
    <label>Service name<input name="name" minLength={2} maxLength={180} defaultValue={service?.name ?? ""} required /></label>
    <label>Category<input name="category" minLength={2} maxLength={100} defaultValue={service?.category ?? ""} required /></label>
    <label>Type<select name="service_type" defaultValue={service?.service_type ?? "doctor"}><option value="doctor">Doctor</option><option value="diagnostic">Diagnostic</option></select></label>
    <label>Provider name<input name="provider_name" maxLength={180} defaultValue={service?.provider_name ?? ""} /></label>
    <label>Fee (₹)<input name="fee" type="number" min="0" step="0.01" defaultValue={service ? (service.fee_paise / 100).toFixed(2) : "0.00"} required /></label>
  </>;
}
