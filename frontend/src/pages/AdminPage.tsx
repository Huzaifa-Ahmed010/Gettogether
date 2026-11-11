import { type FormEvent, useEffect, useRef, useState } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../components/AuthContext";
import SiteLayout from "../components/SiteLayout";
import {
  DIRECTORY_PAGE_SIZE,
  cancelManagedBooking,
  completeManagedBooking,
  createFacilityService,
  confirmManagedBooking,
  downloadBookingDocument,
  deleteManagedFacility,
  deleteManagedService,
  getAdminDashboard,
  getBookingDocuments,
  getManagedBookings,
  getManagedFacilities,
  getManagedServices,
  getManagedUsers,
  recordManagedBookingPayment,
  rejectManagedBooking,
  submitFacilityOnboarding,
  updateManagedFacility,
  updateManagedService,
  updateManagedUser,
  verifyBooking,
  type AdminBooking,
  type AdminDashboard,
  type AdminUser,
  type BookingDocument,
  type Facility,
  type ManagedService,
} from "../api/client";
import SubscriptionPanel from "./SubscriptionPanel";

type AdminTab = "overview" | "facilities" | "directory" | "bookings" | "accounts" | "subscriptions";

function errorText(error: unknown) {
  return error instanceof Error
    ? error.message.replace(/^API error \d+: /, "")
    : "The request could not be completed.";
}

function formatAppointment(value: string) {
  return new Date(value).toLocaleString();
}

function formatMoney(amountPaise: number, currency: string) {
  return new Intl.NumberFormat("en-IN", { style: "currency", currency }).format(amountPaise / 100);
}

export default function AdminPage() {
  const { user } = useAuth();
  const isPlatformAdmin = user?.role === "platform_admin";
  const canManage = isPlatformAdmin || user?.role === "facility_staff";
  const [tab, setTab] = useState<AdminTab>(isPlatformAdmin ? "overview" : "directory");
  const [dashboard, setDashboard] = useState<AdminDashboard | null>(null);
  const [facilities, setFacilities] = useState<Facility[]>([]);
  const [selectedFacilityId, setSelectedFacilityId] = useState<number | null>(null);
  const [services, setServices] = useState<ManagedService[]>([]);
  const [bookings, setBookings] = useState<AdminBooking[]>([]);
  const [accounts, setAccounts] = useState<AdminUser[]>([]);
  const [accountsHaveMore, setAccountsHaveMore] = useState(false);
  const [loadingMoreAccounts, setLoadingMoreAccounts] = useState(false);
  const [bookingStatus, setBookingStatus] = useState("");
  const [codes, setCodes] = useState<Record<number, string>>({});
  const [documentsByBooking, setDocumentsByBooking] = useState<Record<number, BookingDocument[]>>({});
  const [documentsLoaded, setDocumentsLoaded] = useState<Record<number, boolean>>({});
  const [documentsLoadingId, setDocumentsLoadingId] = useState<number | null>(null);
  const [downloadingDocumentId, setDownloadingDocumentId] = useState<number | null>(null);
  const [paymentSavingId, setPaymentSavingId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [busyDirectoryActions, setBusyDirectoryActions] = useState<Set<string>>(() => new Set());
  const [savingAccountAction, setSavingAccountAction] = useState<{
    accountId: number;
    action: "save" | "toggle";
  } | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const errorRef = useRef<HTMLParagraphElement>(null);

  const selectedFacility = facilities.find((facility) => facility.id === selectedFacilityId) ?? null;

  useEffect(() => {
    if (error) errorRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [error]);

  function isDirectoryActionBusy(action: string) {
    return busyDirectoryActions.has(action);
  }

  function isFacilityBusy(facilityId: number) {
    return [...busyDirectoryActions].some((action) => action.startsWith(`facility:${facilityId}:`));
  }

  function isServiceBusy(serviceId: number) {
    return [...busyDirectoryActions].some((action) => action.startsWith(`service:${serviceId}:`));
  }

  function setDirectoryActionBusy(action: string, busy: boolean) {
    setBusyDirectoryActions((current) => {
      const next = new Set(current);
      if (busy) next.add(action);
      else next.delete(action);
      return next;
    });
  }

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
    });
    setBookings(result);
  }

  async function loadAccounts() {
    if (!isPlatformAdmin) return;
    const items: AdminUser[] = [];
    let hasMore = true;
    for (let offset = 0; hasMore && offset < Math.max(DIRECTORY_PAGE_SIZE, accounts.length); offset += DIRECTORY_PAGE_SIZE) {
      const page = await getManagedUsers({ offset });
      items.push(...page);
      hasMore = page.length === DIRECTORY_PAGE_SIZE;
    }
    setAccounts(items);
    setAccountsHaveMore(hasMore);
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
    if (user?.role !== "facility_staff" || selectedFacilityId === null) {
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
  }, [selectedFacilityId, user?.role]);

  useEffect(() => {
    if (user?.role !== "facility_staff" || tab !== "bookings") return;
    let active = true;
    getManagedBookings({
      status: bookingStatus || undefined,
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
  }, [bookingStatus, tab, user?.role]);

  useEffect(() => {
    if (!canManage || !isPlatformAdmin || tab !== "accounts") return;
    let active = true;
    getManagedUsers()
      .then((items) => {
        if (active) {
          setAccounts(items);
          setAccountsHaveMore(items.length === DIRECTORY_PAGE_SIZE);
        }
      })
      .catch((reason: unknown) => {
        if (active) setError(errorText(reason));
      });
    return () => {
      active = false;
    };
  }, [canManage, isPlatformAdmin, tab]);

  async function loadMoreAccounts() {
    setLoadingMoreAccounts(true);
    setError("");
    try {
      const items = await getManagedUsers({ offset: accounts.length });
      setAccounts((current) => [...current, ...items]);
      setAccountsHaveMore(items.length === DIRECTORY_PAGE_SIZE);
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setLoadingMoreAccounts(false);
    }
  }

  async function submitFacilityOnboardingRequest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    setDirectoryActionBusy("facility:onboarding", true);
    setError("");
    setNotice("");
    try {
      const created = await submitFacilityOnboarding({
        name: String(form.get("name")),
        facility_type: String(form.get("facility_type")) as Facility["facility_type"],
        address: String(form.get("address")),
        city: String(form.get("city")),
        phone: String(form.get("phone") ?? ""),
        description: String(form.get("description") ?? ""),
        timezone: String(form.get("timezone") ?? "Asia/Kolkata"),
      });
      setNotice("Facility submitted. It will remain unavailable to patients until a platform administrator approves it.");
      await loadDirectory();
      setSelectedFacilityId(created.id);
      formElement.reset();
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setDirectoryActionBusy("facility:onboarding", false);
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
      description: String(form.get("description") ?? ""),
      timezone: String(form.get("timezone") ?? "Asia/Kolkata"),
    };
    const action = `facility:${selectedFacility.id}:save`;
    setDirectoryActionBusy(action, true);
    setError("");
    setNotice("");
    try {
      await updateManagedFacility(selectedFacility.id, payload);
      setNotice("Facility details saved.");
      await loadDirectory();
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setDirectoryActionBusy(action, false);
    }
  }

  async function submitService(event: FormEvent<HTMLFormElement>, existing?: ManagedService) {
    event.preventDefault();
    if (!selectedFacility) return;
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const action = existing
      ? `service:${existing.id}:save`
      : `service:create:${selectedFacility.id}`;
    const payload = {
      name: String(form.get("name")),
      category: String(form.get("category")),
      service_type: String(form.get("service_type")) as ManagedService["service_type"],
      provider_name: String(form.get("provider_name") ?? ""),
      fee_paise: Math.round(Number(form.get("fee")) * 100),
    };
    setDirectoryActionBusy(action, true);
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
      setDirectoryActionBusy(action, false);
    }
  }

  async function toggleFacility(facility: Facility) {
    const action = facility.is_active ? "deactivate" : "activate";
    if (!window.confirm(`${action[0].toUpperCase()}${action.slice(1)} ${facility.name}?`)) return;
    const busyAction = `facility:${facility.id}:status`;
    setDirectoryActionBusy(busyAction, true);
    setError("");
    setNotice("");
    try {
      await updateManagedFacility(facility.id, { is_active: !facility.is_active });
      setNotice(facility.is_active ? "Facility deactivated." : "Facility activated.");
      await loadDirectory();
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setDirectoryActionBusy(busyAction, false);
    }
  }

  async function deleteFacility(facility: Facility) {
    if (!window.confirm(`Permanently delete ${facility.name}? This cannot be undone.`)) return;
    const busyAction = `facility:${facility.id}:delete`;
    setDirectoryActionBusy(busyAction, true);
    setError("");
    setNotice("");
    try {
      const result = await deleteManagedFacility(facility.id);
      setNotice(result.message);
      await loadDirectory();
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setDirectoryActionBusy(busyAction, false);
    }
  }

  async function toggleService(service: ManagedService) {
    if (!selectedFacility) return;
    const busyAction = `service:${service.id}:status`;
    setDirectoryActionBusy(busyAction, true);
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
      setDirectoryActionBusy(busyAction, false);
    }
  }

  async function deleteService(service: ManagedService) {
    if (!selectedFacility) return;
    if (!window.confirm(`Permanently delete ${service.name}? This cannot be undone.`)) return;
    const busyAction = `service:${service.id}:delete`;
    setDirectoryActionBusy(busyAction, true);
    setError("");
    setNotice("");
    try {
      const result = await deleteManagedService(selectedFacility.id, service.id);
      setNotice(result.message);
      setServices(await getManagedServices(selectedFacility.id));
      await loadDashboard();
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setDirectoryActionBusy(busyAction, false);
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

  async function confirmBooking(booking: AdminBooking) {
    setSaving(true);
    setError("");
    setNotice("");
    try {
      await confirmManagedBooking(booking.id);
      setNotice("Appointment confirmed. The patient can now retrieve their check-in code.");
      await loadBookings();
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setSaving(false);
    }
  }

  async function rejectBooking(booking: AdminBooking) {
    const reason = window.prompt("Why is this appointment request being rejected?");
    if (reason === null) return;
    if (reason.trim().length < 5) {
      setError("Enter a rejection reason of at least five characters.");
      return;
    }
    setSaving(true);
    setError("");
    setNotice("");
    try {
      await rejectManagedBooking(booking.id, reason.trim());
      setNotice("Appointment request rejected.");
      await loadBookings();
    } catch (failure) {
      setError(errorText(failure));
    } finally {
      setSaving(false);
    }
  }

  async function completeBooking(booking: AdminBooking) {
    setSaving(true);
    setError("");
    setNotice("");
    try {
      await completeManagedBooking(booking.id);
      setNotice("Appointment marked complete.");
      await loadBookings();
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

  async function submitPaymentCollection(event: FormEvent<HTMLFormElement>, booking: AdminBooking) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setPaymentSavingId(booking.id);
    setError("");
    setNotice("");
    try {
      await recordManagedBookingPayment(booking.id, String(form.get("reference") ?? ""));
      setNotice("Facility payment recorded.");
      await loadBookings();
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setPaymentSavingId(null);
    }
  }

  async function loadBookingDocuments(bookingId: number) {
    setError("");
    setDocumentsLoadingId(bookingId);
    try {
      const documents = await getBookingDocuments(bookingId);
      setDocumentsByBooking((current) => ({ ...current, [bookingId]: documents }));
      setDocumentsLoaded((current) => ({ ...current, [bookingId]: true }));
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setDocumentsLoadingId(null);
    }
  }

  async function downloadDocument(bookingId: number, file: BookingDocument) {
    setError("");
    setDownloadingDocumentId(file.id);
    try {
      await downloadBookingDocument(bookingId, file);
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setDownloadingDocumentId(null);
    }
  }

  async function submitAccountUpdate(event: FormEvent<HTMLFormElement>, account: AdminUser) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const role = String(form.get("role")) as "patient" | "facility_staff";
    const payload: { role: "patient" | "facility_staff"; facility_id?: number | null } = { role };
    if (role === "facility_staff") {
      const selectedFacility = String(form.get("facility_id") ?? "");
      if (selectedFacility) {
        const facilityId = Number(selectedFacility);
        if (!Number.isInteger(facilityId) || facilityId < 1) {
          setError("Choose a valid facility or leave the account unassigned.");
          return;
        }
        payload.facility_id = facilityId;
      } else {
        payload.facility_id = null;
      }
    }
    setSavingAccountAction({ accountId: account.id, action: "save" });
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
      setSavingAccountAction(null);
    }
  }

  async function toggleAccount(account: AdminUser) {
    const action = account.is_active ? "deactivate" : "activate";
    if (!window.confirm(`${action[0].toUpperCase()}${action.slice(1)} ${account.name}'s account?`)) return;
    setSavingAccountAction({ accountId: account.id, action: "toggle" });
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
      setSavingAccountAction(null);
    }
  }

  if (!user) return <Navigate to="/login" replace />;
  if (!canManage) {
    return <SiteLayout><main className="admin-page content"><h1>Admin access required</h1><p>Your account does not have permission to manage GetTogether.</p></main></SiteLayout>;
  }

  return <SiteLayout>
    <main className="admin-page content">
      <p className="eyebrow">{isPlatformAdmin ? "PLATFORM ADMINISTRATION" : "FACILITY OPERATIONS"}</p>
      <h1>{isPlatformAdmin ? "Platform admin panel" : "Facility workspace"}</h1>
      {error && <p ref={errorRef} className="notice" role="alert">{error}</p>}
      {notice && <p className="admin-success" role="status">{notice}</p>}
      {loading && <p role="status">Loading management data…</p>}

      {dashboard && <div className="admin-stats">
        <article><span>Active facilities</span><strong>{dashboard.facilities}</strong></article>
        <article><span>Active services</span><strong>{dashboard.services}</strong></article>
        <article><span>Bookings</span><strong>{dashboard.bookings}</strong></article>
        {isPlatformAdmin && <article><span>Accounts</span><strong>{dashboard.users ?? 0}</strong></article>}
      </div>}

      <div className="admin-tabs" role="tablist" aria-label="Admin sections">
        {isPlatformAdmin ? <>
          <button type="button" role="tab" aria-selected={tab === "overview"} onClick={() => setTab("overview")}>Overview</button>
          <button type="button" role="tab" aria-selected={tab === "facilities"} onClick={() => setTab("facilities")}>Facilities</button>
          <button type="button" role="tab" aria-selected={tab === "subscriptions"} onClick={() => setTab("subscriptions")}>Subscriptions</button>
          <button type="button" role="tab" aria-selected={tab === "accounts"} onClick={() => setTab("accounts")}>User accounts</button>
        </> : <>
          <button type="button" role="tab" aria-selected={tab === "directory"} onClick={() => setTab("directory")}>My facility & services</button>
          <button type="button" role="tab" aria-selected={tab === "bookings"} onClick={() => setTab("bookings")}>Appointments</button>
          <button type="button" role="tab" aria-selected={tab === "subscriptions"} onClick={() => setTab("subscriptions")}>Subscription & billing</button>
        </>}
      </div>

      {isPlatformAdmin && tab === "overview" && <section className="admin-panel">
        <div className="admin-panel-heading"><div><p className="eyebrow">SYSTEM SUMMARY</p><h2>Platform overview</h2></div></div>
        <p>These totals provide platform-level visibility. Facility staff handle individual appointment records, payments, and check-in.</p>
      </section>}

      {tab === "subscriptions" && <SubscriptionPanel
        platformAdmin={isPlatformAdmin}
        facilityAvailable={facilities.length > 0}
        userId={user.id}
      />}

      {isPlatformAdmin && tab === "facilities" && <section className="admin-section">
        <section className="admin-panel">
          <div className="admin-panel-heading"><h2>Facilities</h2></div>
          {facilities.length === 0 && <p className="admin-empty">No facilities have been registered yet.</p>}
          <div className="admin-item-list">
            {facilities.map((facility) => <article className="admin-item admin-facility-row" key={facility.id}>
              <div><h3>{facility.name}</h3><p>{facility.city} · {facility.facility_type}</p><p>{facility.description || "No public description"} · {facility.timezone}</p><span className={facility.is_active ? "admin-status active" : "admin-status"}>{facility.is_active ? "Active" : "Inactive"}</span></div>
              <div className="admin-actions"><button type="button" className="secondary-button" disabled={isFacilityBusy(facility.id)} onClick={() => toggleFacility(facility)}>{isDirectoryActionBusy(`facility:${facility.id}:status`) ? "Updating…" : facility.is_active ? "Deactivate" : "Activate"}</button><button type="button" className="danger-button" disabled={isFacilityBusy(facility.id)} onClick={() => deleteFacility(facility)}>{isDirectoryActionBusy(`facility:${facility.id}:delete`) ? "Deleting…" : "Delete"}</button></div>
            </article>)}
          </div>
        </section>
      </section>}

      {!isPlatformAdmin && tab === "directory" && <section className="admin-section">
        <section className="admin-panel">
          <div className="admin-panel-heading"><div><p className="eyebrow">MY FACILITY</p><h2>Facility details</h2></div></div>
          {!selectedFacility && <p className="admin-empty">This staff account is not assigned to a facility.</p>}
          {!selectedFacility && <form className="admin-form admin-form-inline" onSubmit={submitFacilityOnboardingRequest}>
            <h3>Submit a new facility</h3>
            <p>Your facility will stay inactive until a platform administrator reviews and approves it.</p>
            <FacilityFields />
            <button className="primary-link" disabled={busyDirectoryActions.has("facility:onboarding")}>{busyDirectoryActions.has("facility:onboarding") ? "Submitting…" : "Submit for approval"}</button>
          </form>}
          {selectedFacility && <>
            {!selectedFacility.is_active && <p className="admin-guidance" role="status">This facility is awaiting platform-admin approval. Patients cannot find it or request appointments yet.</p>}
            <form key={selectedFacility.id} className="admin-form admin-form-inline" onSubmit={submitFacilityUpdate}>
              <fieldset disabled={!selectedFacility.is_active}>
                <FacilityFields facility={selectedFacility} />
                <button className="primary-link" disabled={isFacilityBusy(selectedFacility.id)}>{isDirectoryActionBusy(`facility:${selectedFacility.id}:save`) ? "Saving…" : "Save facility"}</button>
              </fieldset>
            </form>
            <div className="admin-list-heading"><h3>Doctors & services</h3><span>{services.length} total</span></div>
            {services.length === 0 && <p className="admin-empty">No services have been added to this facility yet.</p>}
            <div className="admin-item-list">
              {services.map((service) => <article className="admin-item" key={service.id}>
                <form className="admin-form admin-item-form" onSubmit={(event) => submitService(event, service)}>
                  <div className="admin-item-heading"><div><h4>{service.name}</h4><span className={service.is_active ? "admin-status active" : "admin-status"}>{service.is_active ? "Active" : "Inactive"}</span></div></div>
                  <fieldset disabled={!selectedFacility.is_active}>
                    <ServiceFields service={service} />
                  <div className="admin-actions">
                    <button className="primary-link" disabled={isServiceBusy(service.id)}>{isDirectoryActionBusy(`service:${service.id}:save`) ? "Saving…" : "Save service"}</button>
                    <button type="button" className="secondary-button" disabled={isServiceBusy(service.id)} onClick={() => toggleService(service)}>{isDirectoryActionBusy(`service:${service.id}:status`) ? "Updating…" : service.is_active ? "Deactivate" : "Activate"}</button>
                    <button type="button" className="danger-button" disabled={isServiceBusy(service.id)} onClick={() => deleteService(service)}>{isDirectoryActionBusy(`service:${service.id}:delete`) ? "Deleting…" : "Delete service"}</button>
                  </div>
                  </fieldset>
                </form>
              </article>)}
            </div>
            {selectedFacility?.is_active && <form className="admin-form admin-add-service" onSubmit={(event) => submitService(event)}>
              <h3>Add a service</h3>
              <ServiceFields />
              <button className="primary-link" disabled={busyDirectoryActions.has(`service:create:${selectedFacility.id}`)}>{busyDirectoryActions.has(`service:create:${selectedFacility.id}`) ? "Saving…" : "Add service"}</button>
            </form>}
          </>}
        </section>
      </section>}

      {!isPlatformAdmin && tab === "bookings" && <section className="admin-panel">
        <div className="admin-panel-heading"><div><p className="eyebrow">APPOINTMENTS</p><h2>Bookings</h2></div>
          <div className="admin-booking-filters">
            <label className="admin-select-label">Status
              <select value={bookingStatus} onChange={(event) => setBookingStatus(event.target.value)}>
                <option value="">All statuses</option><option value="requested">Requested</option><option value="confirmed">Confirmed</option><option value="rejected">Rejected</option><option value="checked_in">Checked in</option><option value="completed">Completed</option><option value="cancelled">Cancelled</option>
              </select>
            </label>
          </div>
        </div>
        {bookings.length === 0 && <p className="admin-empty">No bookings match this filter.</p>}
        <div className="admin-item-list">
          {bookings.map((booking) => <article className="admin-item admin-booking" key={booking.id}>
            <div className="admin-item-heading"><div><h3>{booking.service_name}</h3>{booking.provider_name && <p>{booking.provider_name}</p>}<span className={`admin-status ${booking.status}`}>{booking.status}</span></div><b>{booking.facility_name}</b></div>
            <p>{booking.patient_name} · {booking.patient_email_masked}</p>
            <p>{formatAppointment(booking.appointment_at)}</p>
            {booking.rejection_reason && <p>Rejection reason: {booking.rejection_reason}</p>}
            <p>Payment: {booking.payment_status} · {booking.payment_method === "physical" ? "at facility" : booking.payment_method} · {formatMoney(booking.payment_due_paise, booking.payment_currency)} due</p>
            {booking.payment_status === "paid" && <p>Collected{booking.payment_collector_name ? ` by ${booking.payment_collector_name}` : ""}{booking.payment_collected_at ? ` · ${formatAppointment(booking.payment_collected_at)}` : ""}{booking.payment_reference ? ` · Receipt: ${booking.payment_reference}` : ""}</p>}
            {user?.role === "facility_staff" && <section className="booking-documents">
              <h4>Patient reports and prescriptions</h4>
              {!documentsLoaded[booking.id] ? <button type="button" className="secondary-button" disabled={documentsLoadingId === booking.id} onClick={() => loadBookingDocuments(booking.id)}>{documentsLoadingId === booking.id ? "Loading…" : "View documents"}</button>
                : documentsByBooking[booking.id]?.length
                  ? <ul>{documentsByBooking[booking.id].map((file) => <li key={file.id}>
                    <span>{file.filename} · {(file.size_bytes / (1024 * 1024)).toFixed(2)} MB</span>
                    <button type="button" className="secondary-button" disabled={downloadingDocumentId === file.id} onClick={() => downloadDocument(booking.id, file)}>{downloadingDocumentId === file.id ? "Downloading…" : "Download"}</button>
                  </li>)}</ul>
                  : <p>No documents uploaded for this appointment.</p>}
            </section>}
            {booking.status === "requested" && <div className="admin-actions admin-booking-actions">
              <button type="button" className="primary-link" disabled={saving} onClick={() => confirmBooking(booking)}>Confirm request</button>
              <button type="button" className="danger-button" disabled={saving} onClick={() => rejectBooking(booking)}>Reject request</button>
              {booking.payment_status !== "paid" && <button type="button" className="danger-button" disabled={saving || new Date(booking.appointment_at).getTime() <= Date.now()} onClick={() => cancelBooking(booking)}>Cancel request</button>}
            </div>}
            {booking.status === "confirmed" && <div className="admin-actions admin-booking-actions">
              {booking.payment_status === "unpaid" && <form className="admin-verify-form" onSubmit={(event) => submitPaymentCollection(event, booking)}>
                <label htmlFor={`payment-reference-${booking.id}`}>Receipt or payment reference</label>
                <input id={`payment-reference-${booking.id}`} name="reference" maxLength={120} required />
                <button className="secondary-button" disabled={paymentSavingId === booking.id}>{paymentSavingId === booking.id ? "Recording…" : "Record payment"}</button>
              </form>}
              <form className="admin-verify-form" onSubmit={(event) => submitVerification(event, booking)}>
                <label htmlFor={`booking-code-${booking.id}`}>6-digit check-in code</label>
                <input id={`booking-code-${booking.id}`} value={codes[booking.id] ?? ""} inputMode="numeric" pattern="[0-9]{6}" maxLength={6} required onChange={(event) => setCodes((current) => ({ ...current, [booking.id]: event.target.value.replace(/\D/g, "").slice(0, 6) }))} />
                <button className="secondary-button" disabled={saving}>Check in patient</button>
              </form>
              {booking.payment_status !== "paid" && <button type="button" className="danger-button" disabled={saving || new Date(booking.appointment_at).getTime() <= Date.now()} onClick={() => cancelBooking(booking)}>Cancel booking</button>}
            </div>}
            {booking.status === "checked_in" && <button type="button" className="primary-link" disabled={saving} onClick={() => completeBooking(booking)}>Mark appointment complete</button>}
          </article>)}
        </div>
      </section>}

      {tab === "accounts" && isPlatformAdmin && <section className="admin-panel">
        <div className="admin-panel-heading"><div><p className="eyebrow">ACCESS CONTROL</p><h2>User accounts</h2></div></div>
        <p className="admin-guidance">Email verification is temporarily paused. Dashboard access changes sign the user out. To onboard a new facility, assign facility-staff access without choosing a facility; that person can submit the facility from the Facility workspace. Platform administrator roles are operator-managed and cannot be changed here.</p>
        {accounts.length === 0 && <p className="admin-empty">No accounts are registered yet.</p>}
        <div className="admin-item-list">
          {accounts.map((account) => <article className="admin-item admin-account" key={account.id}>
            <div className="admin-item-heading"><div><h3>{account.name}</h3><p>{account.email}</p></div><span className={account.is_active ? "admin-status active" : "admin-status"}>{account.is_active ? "Active" : "Inactive"}</span></div>
            <p>Current access: {account.role.replace("_", " ")}{account.facility_name ? ` · ${account.facility_name}` : ""} · {account.email_verified ? "Email verification complete" : "Email verification deferred"}</p>
            {account.role !== "platform_admin" && <form className="admin-account-form" onSubmit={(event) => submitAccountUpdate(event, account)}>
              <label>Role<select name="role" defaultValue={account.role === "facility_staff" ? "facility_staff" : "patient"}>
                <option value="patient">Patient</option><option value="facility_staff">Facility staff</option>
              </select></label>
              <label>Assigned facility<select name="facility_id" defaultValue={account.facility_id ?? ""}>
                <option value="">No facility — allow staff onboarding</option>{facilities.filter((facility) => facility.is_active).map((facility) => <option key={facility.id} value={facility.id}>{facility.name}</option>)}
              </select></label>
              <div className="admin-actions"><button className="primary-link" disabled={savingAccountAction?.accountId === account.id}>{savingAccountAction?.accountId === account.id && savingAccountAction.action === "save" ? "Saving…" : "Save access"}</button><button type="button" className="secondary-button" disabled={savingAccountAction?.accountId === account.id} onClick={() => toggleAccount(account)}>{savingAccountAction?.accountId === account.id && savingAccountAction.action === "toggle" ? account.is_active ? "Deactivating…" : "Activating…" : account.is_active ? "Deactivate account" : "Activate account"}</button></div>
            </form>}
          </article>)}
        </div>
        {accountsHaveMore && <button className="secondary-button" disabled={loadingMoreAccounts} onClick={loadMoreAccounts}>{loadingMoreAccounts ? "Loading…" : "Load more accounts"}</button>}
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
    <label>Public description<textarea name="description" maxLength={2000} defaultValue={facility?.description ?? ""} /></label>
    <label>Timezone (IANA)<input name="timezone" maxLength={64} defaultValue={facility?.timezone ?? "Asia/Kolkata"} required /></label>
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
