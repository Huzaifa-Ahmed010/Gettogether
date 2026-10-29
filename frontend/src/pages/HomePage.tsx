import { useEffect, useState } from "react";
import { Activity, ArrowRight, CalendarDays, ChevronRight, ClipboardPlus, FlaskConical, HeartPulse, Search, ShieldCheck, Stethoscope } from "lucide-react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { getFacilities, type Facility } from "../api/client";
import FacilityCard from "../components/FacilityCard";
import SiteLayout from "../components/SiteLayout";

const specialties = [
  { icon: Stethoscope, title: "General Medicine", subtitle: "MD" },
  { icon: HeartPulse, title: "General Physician", subtitle: "MBBS" },
  { icon: Activity, title: "Unani Medicine", subtitle: "BUMS" },
  { icon: ClipboardPlus, title: "Ayurveda", subtitle: "BAMS" },
  { icon: HeartPulse, title: "Homeopathy", subtitle: "BHMS" },
  { icon: ShieldCheck, title: "Surgery", subtitle: "MS" },
];
const diagnostics = [
  { icon: Activity, title: "Ultrasound Abdomen" },
  { icon: HeartPulse, title: "Pregnancy Scan" },
  { icon: FlaskConical, title: "Blood Test / Lab" },
  { icon: ClipboardPlus, title: "X-Ray / Imaging" },
  { icon: Activity, title: "MRI / CT Scan" },
  { icon: HeartPulse, title: "Heart Tests (ECG)" },
];

export default function HomePage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [facilities, setFacilities] = useState<Facility[]>([]);
  const [error, setError] = useState("");
  const city = searchParams.get("city") ?? "";

  useEffect(() => {
    let active = true;
    getFacilities({ city: city || undefined })
      .then((items) => {
        if (active) setFacilities(items);
      })
      .catch(() => {
        if (active) setError("Unable to load partner centers. Check that the API is running and try again.");
      });
    return () => {
      active = false;
    };
  }, [city]);

  function search(query: string) {
    const params = new URLSearchParams();
    if (query.trim()) params.set("search", query.trim());
    if (city.trim()) params.set("city", city.trim());
    const queryString = params.toString();
    navigate(`/search${queryString ? `?${queryString}` : ""}`);
  }

  return <SiteLayout>
    <section className="hero">
      <div className="hero-copy">
        <p className="eyebrow">CARE THAT BRINGS US TOGETHER</p>
        <h1>Your Health Partner — GetTogether</h1>
        <p>Discover trusted hospitals, doctors, and diagnostic services near you.</p>
        <form className="hero-search" onSubmit={(event) => { event.preventDefault(); search(String(new FormData(event.currentTarget).get("search") ?? "")); }}>
          <Search size={19} />
          <input name="search" aria-label="Search healthcare services" placeholder="Search for doctors, hospitals, diagnostics..." />
          <button aria-label="Search"><ArrowRight size={20} /></button>
        </form>
        <div className="trust-row"><span><ShieldCheck size={15} /> Trusted care partners</span><span><CalendarDays size={15} /> Easy appointments</span></div>
      </div>
      <div className="hero-art"><div className="art-circle"><HeartPulse size={92} /></div><div className="art-float float-one"><Stethoscope size={26} /></div><div className="art-float float-two"><ClipboardPlus size={25} /></div><div className="art-float float-three"><Activity size={25} /></div></div>
    </section>
    <main className="content">
      <section className="section">
        <div className="section-heading"><div><p className="eyebrow">FIND THE RIGHT CARE</p><h2>Browse by Doctor Category</h2></div><Link className="text-button" to="/doctors">View all <ChevronRight size={17} /></Link></div>
        <div className="category-grid">{specialties.map(({ icon: Icon, title, subtitle }) => <Link className="category-card" key={title} to={`/doctors?search=${encodeURIComponent(title)}`}><span className="category-icon"><Icon size={29} /></span><b>{subtitle}</b><span>{title}</span></Link>)}</div>
      </section>
      <section className="section">
        <div className="section-heading"><div><p className="eyebrow">TESTS & IMAGING</p><h2>Diagnostics & Scans by Category</h2></div><Link className="text-button" to="/diagnostics">View all <ChevronRight size={17} /></Link></div>
        <div className="category-grid">{diagnostics.map(({ icon: Icon, title }) => <Link className="category-card diagnostic-card" key={title} to={`/diagnostics?search=${encodeURIComponent(title)}`}><span className="category-icon"><Icon size={29} /></span><b>{title}</b><span>Explore services</span></Link>)}</div>
      </section>
      <section className="partner-section" id="hospitals">
        <div className="section-heading"><div><p className="eyebrow">HEALTHCARE AROUND YOU</p><h2>Partner Centers {city ? `in ${city}` : "Near You"}</h2></div><span className="partner-count">{facilities.length} centers</span></div>
        {error && <p className="notice" role="alert">{error}</p>}
        <div className="facility-grid">{facilities.length ? facilities.slice(0, 3).map((facility) => <FacilityCard facility={facility} key={facility.id} />) : !error ? <div className="empty-state"><ClipboardPlus size={30} /><b>No partner centers found yet</b><span>Centers will appear here when added by an authorized administrator.</span></div> : null}</div>
        {facilities.length > 3 && <p className="directory-more"><Link to="/hospitals">Browse all partner centers <ChevronRight size={17} /></Link></p>}
      </section>
      <section className="assistant-banner" id="assistant"><div className="assistant-icon"><HeartPulse size={29} /></div><div><p className="eyebrow">HERE TO HELP</p><h2>Not sure where to start?</h2><p>Our care navigator can help you explore services and navigate GetTogether.</p></div><Link to="/assistant" className="assistant-action">Ask the assistant <ArrowRight size={17} /></Link></section>
      <div id="about" className="about-note"><h2>Care is better together.</h2><p>Find trusted healthcare services and providers in one place.</p></div>
    </main>
  </SiteLayout>;
}
