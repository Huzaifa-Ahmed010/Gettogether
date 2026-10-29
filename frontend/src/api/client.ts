
const configuredApiBaseUrl = import.meta.env.VITE_API_BASE_URL?.replace(/\/+$/, "");
if (import.meta.env.PROD) {
  if (!configuredApiBaseUrl) {
    throw new Error("VITE_API_BASE_URL must be set when building the production frontend.");
  }
  const apiUrl = new URL(configuredApiBaseUrl);
  if (
    apiUrl.protocol !== "https:" ||
    apiUrl.pathname !== "/api/v1" ||
    apiUrl.username ||
    apiUrl.password ||
    apiUrl.search ||
    apiUrl.hash
  ) {
    throw new Error("Production VITE_API_BASE_URL must be HTTPS and end in /api/v1.");
  }
}
const API_BASE = configuredApiBaseUrl ?? "http://localhost:8000/api/v1";
const SESSION_STORAGE_KEY = "gettogether_session";

function getStoredAccessToken(): string | null {
  const storedSession = localStorage.getItem(SESSION_STORAGE_KEY);
  if (!storedSession) return null;
  try {
    const session = JSON.parse(storedSession) as { accessToken?: unknown; expiresAt?: unknown };
    if (typeof session.accessToken === "string" && typeof session.expiresAt === "number" && session.expiresAt > Date.now()) {
      return session.accessToken;
    }
  } catch {
    localStorage.removeItem(SESSION_STORAGE_KEY);
  }
  return null;
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const accessToken = getStoredAccessToken();
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...options.headers,
    },
  });

  if (!response.ok) {
    const body = await response.text();
    let message = body;
    try {
      const error = JSON.parse(body) as { detail?: unknown };
      if (typeof error.detail === "string") message = error.detail;
    } catch {
      message = body;
    }
    throw new Error(
      `API error ${response.status}: ${message}`
    );
  }

  return response.json() as Promise<T>;
}

export type Facility = {
  id: number;
  name: string;
  facility_type: "hospital" | "diagnostic";
  address: string;
  city: string;
  phone: string;
};

export type Service = {
  id: number;
  facility_id: number;
  name: string;
  category: string;
  service_type: "doctor" | "diagnostic";
  provider_name: string;
  fee_paise: number;
  is_active: boolean;
  facility_name: string;
  facility_city: string;
  facility_address: string;
  facility_phone: string;
};

export type Account = {
  id: number;
  name: string;
  email: string;
  created_at: string;
  role: "patient" | "facility_staff" | "platform_admin";
};

export type AccountSession = {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  user: Account;
};

export type RegistrationPending = {
  message: string;
  email: string;
  development_otp?: string | null;
};

export function registerAccount(payload: { name: string; email: string; password: string }) {
  return request<RegistrationPending>("/auth/register", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function loginAccount(payload: { email: string; password: string }) {
  return request<AccountSession>("/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function verifyEmailAddress(payload: { email: string; code: string }) {
  return request<AccountSession>("/auth/verify-email", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function resendEmailVerification(email: string) {
  return request<{ message: string; development_otp?: string | null }>("/auth/resend-verification", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export function requestPasswordReset(email: string) {
  return request<{ message: string; development_otp?: string | null }>("/auth/request-password-reset", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export function completePasswordReset(payload: { email: string; code: string; new_password: string }) {
  return request<{ message: string }>("/auth/reset-password", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export type Booking = {
  id: number;
  facility_id: number;
  service_id: number;
  appointment_at: string;
  payment_method: "physical";
  payment_status: string;
  status: string;
  verification_code?: string;
  facility_name?: string;
  service_name?: string;
};

export function createBooking(payload: {
  facility_id: number;
  service_id: number;
  appointment_at: string;
  payment_method: "physical";
}) {
  return request<Booking>("/bookings", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getMyBookings() {
  return request<Booking[]>("/bookings");
}

export function cancelBooking(bookingId: number) {
  return request<Booking>(`/bookings/${bookingId}/cancel`, { method: "POST" });
}

export function getFacilities(filters?: {
  city?: string;
  facility_type?: "hospital" | "diagnostic";
  search?: string;
}) {
  const params = new URLSearchParams();

  if (filters?.city) params.set("city", filters.city);
  if (filters?.facility_type) {
    params.set("facility_type", filters.facility_type);
  }
  if (filters?.search) params.set("search", filters.search);

  const query = params.toString();
  return request<Facility[]>(
    `/facilities${query ? `?${query}` : ""}`
  );
}

export function searchServices(filters: {
  city?: string;
  search?: string;
  service_type?: Service["service_type"];
}) {
  const params = new URLSearchParams();
  if (filters.service_type) params.set("service_type", filters.service_type);
  if (filters.city) params.set("city", filters.city);
  if (filters.search) params.set("search", filters.search);
  return request<Service[]>(`/services?${params.toString()}`);
}

export function getFacility(facilityId: number) {
  return request<Facility>(`/facilities/${facilityId}`);
}

export function getFacilityServices(facilityId: number) {
  return request<Omit<Service, "facility_name" | "facility_city" | "facility_address" | "facility_phone">[]>(
    `/facilities/${facilityId}/services`
  );
}

export function sendAssistantMessage(message: string) {
  return request<{ reply: string }>("/assistant/chat", {
    method: "POST",
    body: JSON.stringify({ message }),
  });
}
