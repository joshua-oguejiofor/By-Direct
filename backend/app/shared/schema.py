from pydantic import BaseModel, field_validator


class StripedSchema(BaseModel):

    @field_validator("*", mode="before")
    def strip_whitespace(cls, value):
        if isinstance(value, str):
            return value.strip()
        return value
    
    model_config = {
            "populate_by_name": True,
            "from_attributes": True,
            "extra": "ignore"
        }



class LoweredStripedSchema(BaseModel):

    @field_validator("*", mode="before")
    def strip_whitespace(cls, value):
        if isinstance(value, str):
            return value.strip().lower()
        return value

    model_config = {
        "populate_by_name": True,
        "from_attributes": True,
        "extra": "ignore"
    }
    
class SharedResponseSchema(StripedSchema):
    
    model_config = {
            "extra": "ignore",
            "populate_by_name": True,
            "from_attributes": True
        }

