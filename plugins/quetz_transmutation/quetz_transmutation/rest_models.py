from typing import Optional

from pydantic import BaseModel, Field


class PackageSpec(BaseModel):
    package_spec: Optional[str] = Field(None, title="package version specification")
