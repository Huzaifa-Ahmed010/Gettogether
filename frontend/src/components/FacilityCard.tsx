import { ClipboardPlus, MapPin } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { getFacilityImageUrl, type Facility } from "../api/client";

export default function FacilityCard({ facility }: { facility: Facility }) {
  const [imageUnavailable, setImageUnavailable] = useState(false);
  return <article className="facility-card">
    <div className="facility-illustration">{imageUnavailable
      ? <ClipboardPlus size={38} />
      : <img src={getFacilityImageUrl(facility.id)} alt={`${facility.name} facility`} onError={() => setImageUnavailable(true)} />}</div>
    <div className="facility-info">
      <span className="facility-type">{facility.facility_type === "hospital" ? "HOSPITAL" : "DIAGNOSTIC CENTER"}</span>
      <h3>{facility.name}</h3>
      <p><MapPin size={14} />{facility.address}, {facility.city}</p>
      <div className="facility-actions">
        <Link to={`/facilities/${facility.id}`}>View details</Link>
        {facility.phone ? <a className="outline-button" href={`tel:${facility.phone}`}>Call</a> : <span className="contact-unavailable">Phone unavailable</span>}
      </div>
    </div>
  </article>;
}
