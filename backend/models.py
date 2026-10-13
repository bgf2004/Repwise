"""Input boundaries shared by the HTTP API and persisted workout data."""

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


def aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Include a timezone in timestamps, such as Z or -05:00.")
    return value.astimezone(timezone.utc)


class WorkoutCreate(StrictModel):
    pass


class WorkoutUpdate(StrictModel):
    ended_at: datetime | None

    @field_validator("ended_at")
    @classmethod
    def timestamp(cls, value):
        return aware_utc(value) if value is not None else None


class RepDetail(StrictModel):
    index: int = Field(ge=1, le=200)
    down_seconds: float = Field(ge=0, le=120)
    up_seconds: float = Field(ge=0, le=120)
    total_seconds: float = Field(gt=0, le=240)
    range_degrees: float = Field(ge=0, le=180)

    @model_validator(mode="after")
    def phases_fit(self):
        if self.down_seconds + self.up_seconds > self.total_seconds + 0.15:
            raise ValueError("Rep phases cannot exceed total rep time.")
        return self


class SetCreate(StrictModel):
    id: UUID
    exercise: Literal["squat", "curl"]
    weight: float = Field(ge=0, le=2000)
    unit: Literal["lb", "kg"]
    target_reps: int = Field(ge=1, le=200)
    reps: int = Field(ge=0, le=200)
    set_number: int = Field(ge=1, le=100)
    started_at: datetime
    ended_at: datetime
    rest_before_seconds: float | None = Field(default=None, ge=0, le=7200)
    tempo: Literal["natural", "controlled"] = "natural"
    effort_rir: int | None = Field(default=None, ge=0, le=10)
    source: Literal["camera", "manual"]
    rep_details: list[RepDetail] = Field(default_factory=list, max_length=200)
    notes: str = Field(default="", max_length=2000)

    @field_validator("started_at", "ended_at")
    @classmethod
    def timestamps(cls, value):
        return aware_utc(value)

    @model_validator(mode="after")
    def consistent_set(self):
        duration = (self.ended_at - self.started_at).total_seconds()
        if duration < 0:
            raise ValueError("Set end must be at or after its start.")
        if duration > 6 * 3600:
            raise ValueError("A set cannot last longer than six hours.")
        if [rep.index for rep in self.rep_details] != list(range(1, len(self.rep_details) + 1)):
            raise ValueError("Rep detail indexes must start at 1 and be consecutive.")
        if sum(rep.total_seconds for rep in self.rep_details) > duration + 1:
            raise ValueError("Tracked rep timing cannot exceed set duration.")
        if self.source == "manual" and self.rep_details:
            raise ValueError("Manual sets cannot claim camera-tracked rep measurements.")
        return self


class SetUpdate(StrictModel):
    reps: int | None = Field(default=None, ge=0, le=200)
    weight: float | None = Field(default=None, ge=0, le=2000)
    target_reps: int | None = Field(default=None, ge=1, le=200)
    effort_rir: int | None = Field(default=None, ge=0, le=10)
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def non_nullable_fields(self):
        for field in self.model_fields_set - {"effort_rir"}:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null.")
        if not self.model_fields_set:
            raise ValueError("Provide at least one field to update.")
        return self
