import { useEffect, useState } from "react";
import { ClipboardPlus, MapPin, Stethoscope } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { getFacilities, searchServices, type Facility, type Service } from "../api/client";
import FacilityCard from "../components/FacilityCard";
import SiteLayout from "../components/SiteLayout";

type FacilityDirectoryProps = {
  facilityType?: "hospital" | "diagnostic";
};

function useDirectoryParams() {
  const [params] = useSearchParams();
  return {
    search: params.get("search")?.trim() ?? "",
    city: params.get("city")?.trim() ?? "",
  };
}

export function SearchPage() {
  const { search, city } = useDirectoryParams();
  const [facilities, setFacilities] = useState<Facility[]>([]);
  const [services, setServices] = useState<Service[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    Promise.all([
      getFacilities({ search: search || undefined, city: city || undefined }),
      searchServices({ search: search || undefined, city: city || undefined }),
    ])
      .then(([facilityResults, serviceResults]) => {
        if (active) {
          setFacilities(facilityResults);
          setServices(serviceResults);
        }
      })
      .catch(() => { if (active) setError("Could not load search results. Check your connection and try again."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [city, search]);

  return <SiteLayout>
    <main className="directory-page content">
      <p className="eyebrow">FIND CARE NEAR YOU</p>
      <h1>{search ? `Results for “${search}”` : "Search healthcare services"}{city ? ` in ${city}` : ""}</h1>
      <p className="directory-intro">Search providers, services, hospitals, and diagnostic centers by name or location.</p>
      <div className="directory-meta">{loading ? "Searching…" : `${facilities.length + services.length} results found`}</div>
      {error && <p className="notice" role="alert">{error}</p>}
      {!loading && !error && <>
        {facilities.length > 0 && <section className="directory-results"><h2>Healthcare centers</h2><div className="facility-grid">{facilities.map((facility) => <FacilityCard facility={facility} key={facility.id} />)}</div></section>}
        {services.length > 0 && <section className="directory-results"><h2>Doctors & services</h2><div className="service-grid">{services.map((service) => <ServiceCard service={service} key={`${service.facility_id}-${service.id}`} />)}</div></section>}
        {!facilities.length && !services.length && <div className="empty-state"><ClipboardPlus size={30} /><b>No matching healthcare services found</b><span>Try another service or city.</span></div>}
      </>}
    </main>
  </SiteLayout>;
}

function ServiceCard({ service }: { service: Service }) {
  return <article className="service-card">
    <div className="service-icon">{service.service_type === "doctor" ? <Stethoscope size={25} /> : <ClipboardPlus size={25} />}</div>
    <div className="service-details">
      <span className="facility-type">{service.category}</span>
      <h2>{service.name}</h2>
      {service.provider_name && <p>{service.provider_name}</p>}
      <Link to={`/facilities/${service.facility_id}`} className="service-location"><MapPin size={14} />{service.facility_name}, {service.facility_city}</Link>
      <p className="service-fee">₹{(service.fee_paise / 100).toFixed(2)}</p>
    </div>
  </article>;
}

export function FacilityDirectoryPage({ facilityType }: FacilityDirectoryProps) {
  const { search, city } = useDirectoryParams();
  const [facilities, setFacilities] = useState<Facility[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const pageTitle = facilityType === "hospital" ? "Hospitals" : "Healthcare centers";

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    getFacilities({ search: search || undefined, city: city || undefined, facility_type: facilityType })
      .then((result) => { if (active) setFacilities(result); })
      .catch(() => { if (active) setError("Could not load healthcare centers. Check your connection and try again."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [city, facilityType, search]);

  return <SiteLayout>
    <main className="directory-page content">
      <p className="eyebrow">FIND CARE NEAR YOU</p>
      <h1>{search ? `Results for “${search}”` : pageTitle}{city ? ` in ${city}` : ""}</h1>
      <p className="directory-intro">Search trusted hospitals and diagnostic centers by name, location, or service.</p>
      <div className="directory-meta">{loading ? "Searching…" : `${facilities.length} ${facilities.length === 1 ? "center" : "centers"} found`}</div>
      {error && <p className="notice" role="alert">{error}</p>}
      {!loading && !error && <div className="facility-grid">{facilities.length ? facilities.map((facility) => <FacilityCard facility={facility} key={facility.id} />) : <div className="empty-state"><ClipboardPlus size={30} /><b>No centers match your search</b><span>Try a different service or city.</span></div>}</div>}
    </main>
  </SiteLayout>;
}

export function ServiceDirectoryPage({ serviceType }: { serviceType: Service["service_type"] }) {
  const { search, city } = useDirectoryParams();
  const [services, setServices] = useState<Service[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const isDoctor = serviceType === "doctor";

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    searchServices({ search: search || undefined, city: city || undefined, service_type: serviceType })
      .then((result) => { if (active) setServices(result); })
      .catch(() => { if (active) setError("Could not load services. Check your connection and try again."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [city, search, serviceType]);

  return <SiteLayout>
    <main className="directory-page content">
      <p className="eyebrow">{isDoctor ? "FIND A PROVIDER" : "TESTS & IMAGING"}</p>
      <h1>{isDoctor ? "Find doctors" : "Find diagnostics"}{search ? ` for “${search}”` : ""}{city ? ` in ${city}` : ""}</h1>
      <p className="directory-intro">{isDoctor ? "Explore care providers and specialties from our partner centers." : "Explore diagnostic tests and imaging services from our partner centers."}</p>
      <div className="directory-meta">{loading ? "Searching…" : `${services.length} ${services.length === 1 ? "service" : "services"} found`}</div>
      {error && <p className="notice" role="alert">{error}</p>}
      {!loading && !error && <div className="service-grid">{services.length ? services.map((service) => <ServiceCard service={service} key={`${service.facility_id}-${service.id}`} />) : <div className="empty-state"><ClipboardPlus size={30} /><b>No matching services found</b><span>Try another specialty, test, or city.</span></div>}</div>}
    </main>
  </SiteLayout>;
}
