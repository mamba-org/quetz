from fastapi import APIRouter

router = APIRouter()

@router.get(
    "/api/tos"
)
def get_tos():

    return {"message": "Hello world!"}
