from sqlalchemy import Column, ForeignKey, String
from sqlalchemy.orm import backref, relationship

from quetz.db_models import UUID, Base


class CondaSuggestMetadata(Base):
    __tablename__ = "quetz_conda_suggest_metadata"

    version_id = Column(UUID, ForeignKey("package_versions.id"), primary_key=True)
    package_version = relationship(
        "PackageVersion",
        backref=backref("files", uselist=False, cascade="delete,all"),
    )
    data = Column(String)
