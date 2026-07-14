from __future__ import annotations

from pydantic import BaseModel, Field


class ExperimentInput(BaseModel):
    patientNumber: str | None = None
    height: float | None = Field(default=None, description="cm")
    age: int | None = Field(default=None, description="years")
    weight: float | None = Field(default=None, description="kg")
    properties: dict = Field(default_factory=dict)


class ExerciseInput(BaseModel):
    properties: dict = Field(default_factory=dict)
