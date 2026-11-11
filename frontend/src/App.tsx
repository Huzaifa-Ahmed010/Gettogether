import { BrowserRouter, Navigate, Routes, Route } from "react-router-dom";
import HomePage from "./pages/HomePage";
import LoginPage from "./pages/LoginPage";
import DoctorSearchPage from "./pages/DoctorSearchPage";
import DiagnosticsPage from "./pages/DiagnosticsPage";
import { FacilityDirectoryPage, SearchPage } from "./pages/DirectoryPages";
import FacilityDetailPage from "./pages/FacilityDetailPage";
import AssistantPage from "./pages/AssistantPage";
import NotFoundPage from "./pages/NotFoundPage";
import { AuthProvider } from "./components/AuthContext";
import MyBookingsPage from "./pages/MyBookingsPage";
import PasswordResetPage from "./pages/PasswordResetPage";
import AdminPage from "./pages/AdminPage";
import { useAuth } from "./components/AuthContext";

function RolePanel({ role }: { role: "platform_admin" | "facility_staff" }) {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  if (user.role !== role) {
    return <Navigate to={user.role === "platform_admin" ? "/platform" : user.role === "facility_staff" ? "/facility" : "/"} replace />;
  }
  return <AdminPage key={role} />;
}

function ManagementRedirect() {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  return <Navigate to={user.role === "platform_admin" ? "/platform" : user.role === "facility_staff" ? "/facility" : "/"} replace />;
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/reset-password" element={<PasswordResetPage />} />
          <Route path="/doctors" element={<DoctorSearchPage />} />
          <Route path="/diagnostics" element={<DiagnosticsPage />} />
          <Route path="/hospitals" element={<FacilityDirectoryPage facilityType="hospital" />} />
          <Route path="/search" element={<SearchPage />} />
          <Route path="/assistant" element={<AssistantPage />} />
          <Route path="/bookings" element={<MyBookingsPage />} />
          <Route path="/admin" element={<ManagementRedirect />} />
          <Route path="/platform" element={<RolePanel role="platform_admin" />} />
          <Route path="/facility" element={<RolePanel role="facility_staff" />} />
          <Route path="/facilities/:facilityId" element={<FacilityDetailPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}