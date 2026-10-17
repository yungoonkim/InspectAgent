from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr


Revision = Annotated[StrictStr, Field(pattern=r"^[0-9a-f]{64}$")]
ProductId = Annotated[StrictStr, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")]
PositiveVersion = Annotated[StrictInt, Field(ge=1, le=2147483647)]


class RoiInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Rectangle(RoiInput):
    x: StrictInt = Field(ge=0, le=100000)
    y: StrictInt = Field(ge=0, le=100000)
    width: StrictInt = Field(ge=1, le=100000)
    height: StrictInt = Field(ge=1, le=100000)


class Scope(RoiInput):
    video_id: StrictStr = Field(pattern=r"^VID-[0-9]{6}$")
    source_revision: Revision
    source_width: StrictInt = Field(gt=0, le=1920)
    source_height: StrictInt = Field(gt=0, le=1080)
    product_id: ProductId


class CreatePreset(Scope):
    roi: Rectangle


class CreateVersion(RoiInput):
    expected_version: PositiveVersion
    roi: Rectangle


class ApproveVersion(RoiInput):
    version: PositiveVersion


class ActivateVersion(ApproveVersion):
    expected_active_revision: StrictInt = Field(ge=0, le=2147483647)


class RoiError(Exception):
    def __init__(self, status: int, code: str):
        self.status = status
        self.code = code
        super().__init__(code)
