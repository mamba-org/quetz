import logging
import pickle

from fastapi import APIRouter, Depends

from quetz import authorization
from quetz.deps import get_db, get_rules
from quetz.jobs.models import Job

from .jobs import transmutation
from .rest_models import PackageSpec

router = APIRouter()
logger = logging.getLogger("quetz.jobs")

transmutation_serialized = pickle.dumps(transmutation)


@router.put("/api/transmutation", tags=["plugins"])
def put_transmutation(
    package_spec: PackageSpec,
    db=Depends(get_db),
    auth: authorization.Rules = Depends(get_rules),
):
    user = auth.get_user()
    job = Job(
        owner_id=user,
        manifest=transmutation_serialized,
        items_spec=package_spec.package_spec,
    )
    db.add(job)
    db.commit()
