"""
models.py - Core data models
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class FieldSelection(BaseModel):
    """
    Field selection configuration
    """

    selection_type: str  # "basemodel_class" | "basemodel_field" | "enum_value"
    class_name: str
    field_name: Optional[str] = None
    enum_value: Optional[str] = None

    def build_key(self):
        """
        Build unique key for this selection, uses pydantic hierarchy

        Returns:
            String key (e.g., "basemodel_class_ClassName")
        """
        key = f"{self.selection_type}_{self.class_name}"
        if self.field_name:
            key += f"_{self.field_name}"
        if self.enum_value:
            key += f"_{self.enum_value}"
        return key


class Session(BaseModel):
    """
    Session configuration
    """

    id: str
    name: str
    schema_module: str
    root_class: str
    predictions_folder: str
    sample_size: int
    selections: List[FieldSelection]
    created_at: datetime = Field(default_factory=datetime.now)

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}
