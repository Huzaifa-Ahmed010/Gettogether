import { BrowserRouter, Routes, Route } from "react-router-dom";
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
          <Route path="/admin" element={<AdminPage />} />
          <Route path="/facilities/:facilityId" element={<FacilityDetailPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}