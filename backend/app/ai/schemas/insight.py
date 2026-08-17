"""Structured AI output.

The model must return data, not prose, and the data must be validated before it
reaches the database or the UI. If validation fails we fall back to
deterministic analytics rather than showing an unverified answer.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import Confidence


class Evidence(BaseModel):
    """A metric the insight is grounded in.

    Every value here must come from the context CP-Forge supplied. The model is
    instructed never to invent one, and `metrics_used` lets us audit that.
    """

    metric: str = Field(description="Metric name exactly as provided in the context")
    value: str = Field(description="The value from the context, as a string")
    comparison: str | None = Field(
        None, description="Baseline or previous-period value for contrast"
    )


class Recommendation(BaseModel):
    action: str = Field(description="A concrete, doable action")
    reason: str = Field(description="Why this action, grounded in the evidence")


class AIInsightPayload(BaseModel):
    """Schema for daily/weekly/weakness/progress insights."""

    title: str = Field(max_length=120)
    summary: str = Field(max_length=800)
    confidence: Confidence = Confidence.MEDIUM
    diagnosis: str = Field(default="", max_length=1200)
    evidence: list[Evidence] = Field(default_factory=list, max_length=8)
    recommendations: list[Recommendation] = Field(default_factory=list, max_length=5)
    metrics_used: list[str] = Field(default_factory=list, max_length=20)

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class WeaknessItem(BaseModel):
    topic: str
    severity: str = Field(pattern="^(high|medium|low)$")
    evidence: list[str] = Field(default_factory=list, max_length=5)
    root_cause: str
    recommended_action: str
    recommended_difficulty: str | None = None


class WeaknessPayload(BaseModel):
    summary: str = Field(max_length=600)
    confidence: Confidence = Confidence.MEDIUM
    weaknesses: list[WeaknessItem] = Field(default_factory=list, max_length=6)


class StudyDay(BaseModel):
    day: str
    focus: str
    tasks: list[str] = Field(default_factory=list, max_length=5)


class StudyPlanPayload(BaseModel):
    summary: str = Field(max_length=600)
    confidence: Confidence = Confidence.MEDIUM
    days: list[StudyDay] = Field(default_factory=list, max_length=7)
    notes: list[str] = Field(default_factory=list, max_length=5)


def json_schema_for(model: type[BaseModel], name: str) -> dict[str, Any]:
    """Build a strict JSON schema payload for the provider.

    Providers reject schemas with `$ref`/`$defs` in strict mode, so nested
    models are inlined and every object is closed with
    `additionalProperties: false`.
    """
    schema = model.model_json_schema()
    definitions = schema.pop("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                key = node["$ref"].rsplit("/", 1)[-1]
                return resolve(definitions.get(key, {}))
            resolved = {k: resolve(v) for k, v in node.items()}
            if resolved.get("type") == "object":
                resolved.setdefault("additionalProperties", False)
                # Strict mode requires every property to be listed as required.
                if "properties" in resolved:
                    resolved["required"] = list(resolved["properties"].keys())
            return resolved
        if isinstance(node, list):
            return [resolve(item) for item in node]
        return node

    return {"name": name, "schema": resolve(schema)}
