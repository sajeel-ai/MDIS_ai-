"""Patient API schemas."""

from typing import List, Optional
from pydantic import BaseModel, ConfigDict


class TimelineEvent(BaseModel):
    id: str
    type: str  # 'encounter' | 'document'
    title: str
    date: str
    status: str
    detail: str
    external_encounter_id: Optional[str] = None
    los_hours: Optional[float] = None
    entities: Optional[List[str]] = None


class PatientTimelineResponse(BaseModel):
    patient_id: str
    external_patient_id: Optional[str] = None
    mrn: Optional[str] = None
    full_name: Optional[str] = None
    gender: Optional[str] = None
    dob: Optional[str] = None
    timeline_events: List[TimelineEvent]


class PatientResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    external_patient_id: Optional[str] = None
    mrn: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    gender: Optional[str] = None
    dob: Optional[str] = None
