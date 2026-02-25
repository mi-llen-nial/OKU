from pydantic import BaseModel


class SubjectResponse(BaseModel):
    id: int
    name_ru: str
    name_kz: str

    model_config = {"from_attributes": True}
