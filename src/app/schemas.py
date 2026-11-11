from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.security.config_overrides import ConfigOverrides


class LapRunRequest(BaseModel):
    parameters: dict[str, Any] | None = Field(default=None)
    overrides: ConfigOverrides = Field(default_factory=ConfigOverrides)


class LiftCoastRequest(BaseModel):
    power_limits_kw: list[float] = Field(
        default_factory=lambda: [10.0, 20.0, 30.0, 40.0, 50.0],
        min_length=1,
        max_length=10,
    )
    energy_target_kwh: float = Field(default=0.5, gt=0.0, le=10.0)
    dt: float = Field(default=0.05, gt=0.0, le=1.0)
    parameter_overrides: dict[str, float | int | bool] = Field(
        default_factory=dict,
        max_length=20,
    )

    @field_validator("power_limits_kw")
    @classmethod
    def _bound_each_power_limit(cls, v: list[float]) -> list[float]:
        for x in v:
            if not (0.0 <= x <= 1000.0):
                raise ValueError("power_limits_kw entries must be in [0, 1000]")
        return v


class TyreVerifyRequest(BaseModel):
    lat_dataset: str = Field(min_length=1, max_length=64)
    long_dataset: str = Field(min_length=1, max_length=64)
    model_variant: str = Field(default="tyre_peak_load_clamp", max_length=64)
    rmse_threshold_pct: float = Field(default=12.0, ge=0.0, le=100.0)
    base_mu: float = Field(default=1.0, ge=0.0, le=5.0)
    mu_multiplier: float | None = Field(default=None, ge=0.1, le=2.0)


class SweepRequest(BaseModel):
    param: str = Field(min_length=1, max_length=64)
    values: str = Field(min_length=1, max_length=512)
    steps: int = Field(default=5, ge=2, le=50)
    parameters: dict[str, Any] | None = Field(default=None)
    overrides: ConfigOverrides = Field(default_factory=ConfigOverrides)


class ChatSource(BaseModel):
    file: str
    section: str


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=10000)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=40)


class ChatResponse(BaseModel):
    answer: str
    sources: list[ChatSource]
