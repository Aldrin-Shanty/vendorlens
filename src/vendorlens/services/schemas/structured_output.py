from pydantic import BaseModel, Field, model_validator


class GroundedAnswer(BaseModel):
    answer: str = Field(min_length=1)
    supported: bool
    evidence_ids: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_support(self):
        if self.supported and not self.evidence_ids:
            raise ValueError(
                "Supported answers must reference evidence"
            )

        if not self.supported and self.evidence_ids:
            raise ValueError(
                "Unsupported answers must not reference evidence"
            )

        return self
