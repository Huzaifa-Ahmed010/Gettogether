import { type FormEvent, useEffect, useState } from "react";
import {
  createPlatformSubscriptionPlan,
  extendPlatformSubscription,
  getPlatformAuditEvents,
  getFacilityStaffAccounts,
  getFacilitySubscription,
  getPlatformPayments,
  getPlatformSubscriptions,
  getPlatformSubscriptionPlans,
  getPlatformWebhookEvents,
  getSubscriptionPlans,
  startSubscriptionCheckout,
  transferFacilityBillingOwner,
  updatePlatformSubscriptionPlan,
  type AdminUser,
  type FacilitySubscription,
  type PlatformPayment,
  type PlatformSubscription,
  type PlatformAuditEvent,
  type PlatformWebhookEvent,
  type SubscriptionPlan,
} from "../api/client";

type CheckoutOptions = {
  key: string;
  amount: number;
  currency: string;
  name: string;
  description: string;
  order_id: string;
  prefill: { email: string };
  handler: () => void;
  modal: { ondismiss: () => void };
};

declare global {
  interface Window {
    Razorpay?: new (options: CheckoutOptions) => { open: () => void };
  }
}

let checkoutScript: Promise<void> | null = null;

function loadCheckoutScript() {
  if (window.Razorpay) return Promise.resolve();
  if (!checkoutScript) {
    checkoutScript = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "https://checkout.razorpay.com/v1/checkout.js";
      script.async = true;
      script.onload = () => {
        if (window.Razorpay) {
          resolve();
        } else {
          checkoutScript = null;
          reject(new Error("Payment checkout did not initialize."));
        }
      };
      script.onerror = () => {
        checkoutScript = null;
        reject(new Error("Payment checkout could not be loaded. Please try again."));
      };
      document.head.appendChild(script);
    });
  }
  return checkoutScript;
}

function errorText(error: unknown) {
  return error instanceof Error
    ? error.message.replace(/^API error \d+: /, "")
    : "The request could not be completed.";
}

function formatPrice(pricePaise: number | null, currency = "INR") {
  return pricePaise === null
    ? "Price not set"
    : new Intl.NumberFormat("en-IN", { style: "currency", currency }).format(pricePaise / 100);
}

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleString() : "—";
}

export default function SubscriptionPanel({
  platformAdmin,
  facilityAvailable = true,
  userId,
}: {
  platformAdmin: boolean;
  facilityAvailable?: boolean;
  userId?: number;
}) {
  const [facilitySubscription, setFacilitySubscription] = useState<FacilitySubscription | null>(null);
  const [plans, setPlans] = useState<SubscriptionPlan[]>([]);
  const [subscriptions, setSubscriptions] = useState<PlatformSubscription[]>([]);
  const [payments, setPayments] = useState<PlatformPayment[]>([]);
  const [auditEvents, setAuditEvents] = useState<PlatformAuditEvent[]>([]);
  const [webhookEvents, setWebhookEvents] = useState<PlatformWebhookEvent[]>([]);
  const [staffByFacility, setStaffByFacility] = useState<Record<number, AdminUser[]>>({});
  const [loadingStaffFacility, setLoadingStaffFacility] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [busyPlanId, setBusyPlanId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function load() {
    if (platformAdmin) {
      const [nextPlans, nextSubscriptions, nextPayments, nextAuditEvents, nextWebhookEvents] = await Promise.all([
        getPlatformSubscriptionPlans(),
        getPlatformSubscriptions(),
        getPlatformPayments(),
        getPlatformAuditEvents(),
        getPlatformWebhookEvents(),
      ]);
      setPlans(nextPlans);
      setSubscriptions(nextSubscriptions);
      setPayments(nextPayments);
      setAuditEvents(nextAuditEvents);
      setWebhookEvents(nextWebhookEvents);
    } else if (facilityAvailable) {
      const [nextPlans, nextSubscription] = await Promise.all([
        getSubscriptionPlans(),
        getFacilitySubscription(),
      ]);
      setPlans(nextPlans);
      setFacilitySubscription(nextSubscription);
    }
  }

  useEffect(() => {
    let active = true;
    load().catch((reason: unknown) => {
      if (active) setError(errorText(reason));
    });
    return () => { active = false; };
  }, [platformAdmin, facilityAvailable]);

  async function submitPlan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const amount = String(form.get("price") ?? "").trim();
    const pricePaise = amount === "" ? null : Math.round(Number(amount) * 100);
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await createPlatformSubscriptionPlan({
        name: String(form.get("name")),
        description: String(form.get("description") ?? ""),
        billing_interval: String(form.get("interval")) as SubscriptionPlan["billing_interval"],
        price_paise: pricePaise,
        currency: "INR",
        is_active: form.get("is_active") === "on",
      });
      setNotice("Subscription plan created.");
      formElement.reset();
      await load();
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setBusy(false);
    }
  }

  async function updatePlan(plan: SubscriptionPlan, event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const amount = String(form.get("price") ?? "").trim();
    setBusyPlanId(plan.id);
    setError("");
    setNotice("");
    try {
      await updatePlatformSubscriptionPlan(plan.id, {
        name: String(form.get("name")),
        description: String(form.get("description") ?? ""),
        billing_interval: String(form.get("interval")) as SubscriptionPlan["billing_interval"],
        price_paise: amount === "" ? null : Math.round(Number(amount) * 100),
        is_active: form.get("is_active") === "on",
      });
      setNotice("Subscription plan updated.");
      await load();
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setBusyPlanId(null);
    }
  }

  async function startCheckout(plan: SubscriptionPlan) {
    setBusyPlanId(plan.id);
    setError("");
    setNotice("");
    try {
      const order = await startSubscriptionCheckout(plan.id);
      await loadCheckoutScript();
      if (!window.Razorpay) throw new Error("Payment checkout is unavailable.");
      const checkout = new window.Razorpay({
        key: order.key_id,
        amount: order.amount_paise,
        currency: order.currency,
        name: "GetTogether",
        description: order.description,
        order_id: order.order_id,
        prefill: { email: order.prefill_email },
        handler: () => {
          setNotice("Payment submitted. Access will update after the server verifies the payment.");
          load().catch((reason: unknown) => setError(errorText(reason)));
        },
        modal: {
          ondismiss: () => setNotice("Checkout closed. No subscription access was changed."),
        },
      });
      checkout.open();
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setBusyPlanId(null);
    }
  }

  async function extendSubscription(subscription: PlatformSubscription, event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const days = Number(form.get("days"));
    const reason = String(form.get("reason") ?? "");
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await extendPlatformSubscription(subscription.id, days, reason);
      setNotice(`Subscription for ${subscription.facility_name} extended.`);
      await load();
    } catch (failure) {
      setError(errorText(failure));
    } finally {
      setBusy(false);
    }
  }

  async function loadFacilityStaff(facilityId: number) {
    if (staffByFacility[facilityId]) return;
    setLoadingStaffFacility(facilityId);
    setError("");
    try {
      const accounts = await getFacilityStaffAccounts(facilityId);
      setStaffByFacility((current) => ({ ...current, [facilityId]: accounts }));
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setLoadingStaffFacility(null);
    }
  }

  async function submitOwnerTransfer(
    subscription: PlatformSubscription,
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();
    const userId = Number(new FormData(event.currentTarget).get("user_id"));
    if (!Number.isInteger(userId) || userId < 1) {
      setError("Choose an active staff account as the billing owner.");
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await transferFacilityBillingOwner(subscription.facility_id, userId);
      setNotice(`Billing owner for ${subscription.facility_name} updated.`);
      await load();
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setBusy(false);
    }
  }

  return <section className="admin-section">
    {error && <p className="notice" role="alert">{error}</p>}
    {notice && <p className="admin-success" role="status">{notice}</p>}
    {!platformAdmin && !facilityAvailable ? <section className="admin-panel">
      <h2>Facility setup required</h2>
      <p>Submit your facility for platform approval before opening its subscription account.</p>
    </section> : platformAdmin ? <>
      <section className="admin-panel">
        <div className="admin-panel-heading"><div><p className="eyebrow">BILLING SETUP</p><h2>Subscription plans</h2></div></div>
        <p>Prices are optional until you choose them. A plan must have a positive price before it can be activated.</p>
        <form className="admin-form admin-form-inline" onSubmit={submitPlan}>
          <label>Plan name<input name="name" minLength={2} maxLength={100} required /></label>
          <label>Description<input name="description" maxLength={500} /></label>
          <label>Billing interval<select name="interval" defaultValue="monthly"><option value="monthly">Monthly</option><option value="quarterly">Quarterly</option><option value="yearly">Yearly</option></select></label>
          <label>Price (₹)<input name="price" type="number" min="0.01" step="0.01" /></label>
          <label><input name="is_active" type="checkbox" /> Available for purchase</label>
          <button className="primary-link" disabled={busy}>{busy ? "Saving…" : "Create plan"}</button>
        </form>
        <div className="admin-item-list">
          {plans.map((plan) => <article className="admin-item" key={plan.id}>
            <form className="admin-form admin-item-form" onSubmit={(event) => updatePlan(plan, event)}>
              <div className="admin-item-heading"><div><h3>{plan.name}</h3><span className={plan.is_active ? "admin-status active" : "admin-status"}>{plan.is_active ? "Active" : "Inactive"}</span></div></div>
              <label>Plan name<input name="name" minLength={2} maxLength={100} defaultValue={plan.name} required /></label>
              <label>Description<input name="description" maxLength={500} defaultValue={plan.description} /></label>
              <label>Billing interval<select name="interval" defaultValue={plan.billing_interval}><option value="monthly">Monthly</option><option value="quarterly">Quarterly</option><option value="yearly">Yearly</option></select></label>
              <label>Price (₹)<input name="price" type="number" min="0.01" step="0.01" defaultValue={plan.price_paise === null ? "" : (plan.price_paise / 100).toFixed(2)} /></label>
              <label><input name="is_active" type="checkbox" defaultChecked={plan.is_active} /> Available for purchase</label>
              <button className="primary-link" disabled={busyPlanId === plan.id}>{busyPlanId === plan.id ? "Saving…" : "Save plan"}</button>
            </form>
          </article>)}
          {!plans.length && <p className="admin-empty">No subscription plans have been configured.</p>}
        </div>
      </section>
      <section className="admin-panel">
        <div className="admin-panel-heading"><div><p className="eyebrow">FACILITY ACCESS</p><h2>Subscriptions</h2></div></div>
        <div className="admin-item-list">
          {subscriptions.map((subscription) => <article className="admin-item" key={subscription.id}>
            <div className="admin-item-heading"><div><h3>{subscription.facility_name}</h3><p>{subscription.plan_name ?? "No paid plan"} · {subscription.status}</p></div><span className={subscription.facility_active ? "admin-status active" : "admin-status"}>{subscription.facility_active ? "Facility active" : "Awaiting approval"}</span></div>
            <p>Current period ends: {formatDate(subscription.current_period_end)} · Grace ends: {formatDate(subscription.grace_period_end)}</p>
            <form className="admin-form admin-form-inline" onSubmit={(event) => extendSubscription(subscription, event)}>
              <label>Extension days<input name="days" type="number" min="1" max="365" defaultValue="30" required /></label>
              <label>Audited reason<input name="reason" minLength={5} maxLength={500} required /></label>
              <button className="secondary-button" disabled={busy}>{busy ? "Saving…" : "Extend access"}</button>
            </form>
            <details onToggle={(event) => {
              if (event.currentTarget.open) void loadFacilityStaff(subscription.facility_id);
            }}>
              <summary>Billing owner: {subscription.owner_user_id ?? "not assigned"}</summary>
              {loadingStaffFacility === subscription.facility_id
                ? <p role="status">Loading assigned staff…</p>
                : <form className="admin-form admin-form-inline" onSubmit={(event) => submitOwnerTransfer(subscription, event)}>
                  <label>New billing owner<select name="user_id" defaultValue={subscription.owner_user_id ?? ""} required>
                    <option value="">Choose active staff</option>
                    {(staffByFacility[subscription.facility_id] ?? []).map((account) => <option key={account.id} value={account.id}>{account.name} · {account.email}</option>)}
                  </select></label>
                  <button className="secondary-button" disabled={busy || !staffByFacility[subscription.facility_id]?.length}>{busy ? "Saving…" : "Transfer billing owner"}</button>
                </form>}
            </details>
          </article>)}
          {!subscriptions.length && <p className="admin-empty">Facilities appear here when their first subscription checkout is started.</p>}
        </div>
      </section>
      <section className="admin-panel">
        <div className="admin-panel-heading"><div><p className="eyebrow">PAYMENT HISTORY</p><h2>Subscription payments</h2></div></div>
        <div className="admin-item-list">
          {payments.map((payment) => <article className="admin-item" key={payment.id}>
            <h3>{payment.facility_name} · {payment.plan_name_snapshot}</h3>
            <p>{formatPrice(payment.amount_paise, payment.currency)} · {payment.status} · {formatDate(payment.paid_at)}</p>
            <p>Order: {payment.gateway_order_id ?? "Not created"}{payment.failure_reason ? ` · ${payment.failure_reason}` : ""}</p>
          </article>)}
          {!payments.length && <p className="admin-empty">No subscription payments have been recorded.</p>}
        </div>
      </section>
      <section className="admin-panel">
        <div className="admin-panel-heading"><div><p className="eyebrow">PAYMENT DELIVERY</p><h2>Webhook events</h2></div></div>
        <div className="admin-item-list">
          {webhookEvents.map((event) => <article className="admin-item" key={event.id}>
            <h3>{event.gateway} · {event.event_type} · {event.processing_status}</h3>
            <p>Event: {event.gateway_event_id} · Received: {formatDate(event.received_at)}</p>
            <p>Payload SHA-256: {event.payload_sha256}</p>
          </article>)}
          {!webhookEvents.length && <p className="admin-empty">No signed payment webhooks have been received.</p>}
        </div>
      </section>
      <section className="admin-panel">
        <div className="admin-panel-heading"><div><p className="eyebrow">ADMINISTRATION HISTORY</p><h2>Recent audit events</h2></div></div>
        <div className="admin-item-list">
          {auditEvents.map((event) => <article className="admin-item" key={event.id}>
            <h3>{event.action} · {event.resource_type}{event.resource_id === null ? "" : ` #${event.resource_id}`}</h3>
            <p>{formatDate(event.created_at)} · Actor: {event.actor_user_id ?? "system"}</p>
            {event.details && <p>{event.details}</p>}
          </article>)}
          {!auditEvents.length && <p className="admin-empty">No audit events have been recorded.</p>}
        </div>
      </section>
    </> : <>
      <section className="admin-panel">
        <div className="admin-panel-heading"><div><p className="eyebrow">FACILITY SUBSCRIPTION</p><h2>{facilitySubscription?.facility_name ?? "Subscription"}</h2></div></div>
        {facilitySubscription && <>
          <p>Access status: <strong>{facilitySubscription.status.replaceAll("_", " ")}</strong></p>
          {facilitySubscription.plan_name && <p>{facilitySubscription.plan_name} · {formatPrice(facilitySubscription.price_paise, facilitySubscription.currency)}</p>}
          <p>Current period ends: {formatDate(facilitySubscription.current_period_end)} · Grace ends: {formatDate(facilitySubscription.grace_period_end)}</p>
          {facilitySubscription.notices.map((message, index) => <p className="admin-guidance" key={`${index}-${message}`}>{message}</p>)}
          {facilitySubscription.owner_user_id !== userId && <p className="admin-guidance">Only the designated billing owner can start or renew a subscription. Ask the platform administrator to update the facility billing owner.</p>}
        </>}
      </section>
      <section className="admin-panel">
        <div className="admin-panel-heading"><div><p className="eyebrow">PLANS & RENEWAL</p><h2>Available plans</h2></div></div>
        <p>Payment does not grant access immediately. The platform activates or renews access only after Razorpay verifies the payment server-to-server.</p>
        <div className="admin-item-list">
          {plans.map((plan) => <article className="admin-item" key={plan.id}>
            <h3>{plan.name} · {formatPrice(plan.price_paise, plan.currency)}</h3>
            <p>{plan.billing_interval} · {plan.description}</p>
            <button type="button" className="primary-link" disabled={busyPlanId === plan.id || plan.price_paise === null || facilitySubscription?.owner_user_id !== userId} onClick={() => startCheckout(plan)}>
              {busyPlanId === plan.id ? "Opening checkout…" : facilitySubscription?.id ? "Renew subscription" : "Choose plan"}
            </button>
          </article>)}
          {!plans.length && <p className="admin-empty">No paid plans are available yet. Contact the platform administrator.</p>}
        </div>
      </section>
      <section className="admin-panel">
        <div className="admin-panel-heading"><div><p className="eyebrow">PAYMENT HISTORY</p><h2>Recent payments</h2></div></div>
        <div className="admin-item-list">
          {facilitySubscription?.payments.map((payment) => <article className="admin-item" key={payment.id}>
            <h3>{payment.plan_name_snapshot} · {formatPrice(payment.amount_paise, payment.currency)}</h3>
            <p>{payment.status} · {formatDate(payment.paid_at)}</p>
            {payment.failure_reason && <p>{payment.failure_reason}</p>}
          </article>)}
          {!facilitySubscription?.payments.length && <p className="admin-empty">No subscription payments yet.</p>}
        </div>
      </section>
    </>}
  </section>;
}
