import { type FormEvent, type ReactNode, useEffect, useState } from "react";
import { ArrowRight, MapPin, Search } from "lucide-react";
import { Link, NavLink, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import Brand from "./Brand";
import { useAuth } from "./AuthContext";

export default function SiteLayout({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const [search, setSearch] = useState(searchParams.get("search") ?? "");
  const [city, setCity] = useState(searchParams.get("city") ?? "");
  const { user } = useAuth();

  useEffect(() => {
    setSearch(searchParams.get("search") ?? "");
    setCity(searchParams.get("city") ?? "");
  }, [location.pathname, searchParams]);

  useEffect(() => {
    if (!location.hash) return;
    document.getElementById(decodeURIComponent(location.hash.slice(1)))?.scrollIntoView({ behavior: "smooth" });
  }, [location.hash, location.pathname]);

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const params = new URLSearchParams();
    if (search.trim()) params.set("search", search.trim());
    if (city.trim()) params.set("city", city.trim());
    const query = params.toString();
    navigate(`/search${query ? `?${query}` : ""}`);
  }

  return <div className="page-shell">
    <header className="topbar">
      <Link className="brand-link" to="/" aria-label="GetTogether home"><Brand /></Link>
      <form className="nav-search" role="search" onSubmit={submitSearch}>
        <Search size={17} aria-hidden="true" />
        <input aria-label="Search healthcare services" placeholder="Search doctors, hospitals, diagnostics..." value={search} onChange={(event) => setSearch(event.target.value)} />
        <button className="header-search-submit" aria-label="Submit search"><ArrowRight size={16} /></button>
      </form>
      <label className="city-select"><MapPin size={16} aria-hidden="true" /><input aria-label="City" placeholder="Any city" value={city} onChange={(event) => setCity(event.target.value)} /></label>
      <nav aria-label="Main navigation">
        <NavLink to="/hospitals">Hospitals</NavLink>
        <NavLink to="/doctors">Doctors</NavLink>
        <NavLink to="/diagnostics">Diagnostics</NavLink>
        <NavLink to="/assistant">Assistant</NavLink>
        <Link to="/#about">About</Link>
        {user && <NavLink to="/bookings">My bookings</NavLink>}
      </nav>
      <Link className="login-link" to="/login">{user ? user.name : "Sign in"}</Link>
    </header>
    {children}
    <footer className="site-footer">
      <Link className="brand-link" to="/" aria-label="GetTogether home"><Brand /></Link>
      <span>Healthcare discovery, made simpler.</span>
      <span>© {new Date().getFullYear()} GetTogether</span>
    </footer>
  </div>;
}
