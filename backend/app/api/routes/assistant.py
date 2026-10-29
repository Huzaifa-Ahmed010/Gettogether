from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Facility, Service

router = APIRouter(prefix="/assistant", tags=["care navigation"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


@router.post("/chat")
def chat(payload: ChatRequest, db: Session = Depends(get_db)):
    """Answer navigation questions from the service directory without requiring an LLM."""
    message = payload.message.strip()
    normalized = message.casefold()
    if not message:
        return {"reply": "Tell me which type of care or service you are looking for."}

    if any(term in normalized for term in ("emergency", "urgent", "chest pain", "can't breathe", "cannot breathe")):
        return {
            "reply": (
                "If someone may be experiencing a medical emergency, contact your local emergency "
                "services or go to the nearest emergency department now. I can help with non-emergency "
                "service navigation."
            )
        }

    words = [
        word.strip(".,!?;:'\"()[]{}")
        for word in normalized.split()
        if len(word.strip(".,!?;:'\"()[]{}")) >= 3
        and word.strip(".,!?;:'\"()[]{}") not in {
            "the", "and", "for", "with", "near", "find", "need", "want", "looking",
            "where", "what", "which", "please", "help", "can", "you", "are",
        }
    ]

    services = []
    if words:
        conditions = []
        for word in words[:8]:
            term = f"%{word}%"
            conditions.extend(
                (
                    Service.name.ilike(term),
                    Service.category.ilike(term),
                    Service.provider_name.ilike(term),
                    Facility.name.ilike(term),
                    Facility.city.ilike(term),
                )
            )
        services = (
            db.query(Service, Facility)
            .join(Facility, Service.facility_id == Facility.id)
            .filter(Service.is_active.is_(True), Facility.is_active.is_(True), or_(*conditions))
            .order_by(Service.name, Facility.name)
            .limit(5)
            .all()
        )

    if not services:
        return {
            "reply": (
                "I can help you find doctors, hospitals, and diagnostic services listed on GetTogether. "
                "Try a specialty, test, provider, or city. I can't diagnose conditions or recommend treatment. "
                "For urgent symptoms, contact local emergency services."
            )
        }

    results = [
        f"- {service.name} ({service.category}) at {facility.name}, {facility.city}"
        for service, facility in services
    ]
    return {
        "reply": (
            "Here are matching services from the GetTogether directory:\n"
            + "\n".join(results)
            + "\n\nPlease contact the provider to confirm availability. This assistant can't diagnose or recommend treatment."
        )
    }
