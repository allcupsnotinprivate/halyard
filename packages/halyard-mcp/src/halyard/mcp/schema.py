"""JSON Schema tailored for tool contracts.

A tool's input schema is what the model fills in, so computed, read-only and
deprecated fields have no place there. This generator drops them; everything
else is the plain pydantic schema already derived for the invocable.
"""

from typing import Any

from pydantic import BaseModel
from pydantic.json_schema import GenerateJsonSchema, JsonSchemaValue
from pydantic_core import CoreSchema, PydanticOmit


class ToolInputSchemaGenerator(GenerateJsonSchema):
    """Omit read-only and deprecated fields from an input schema."""

    def generate_inner(self, schema: CoreSchema | Any) -> JsonSchemaValue:
        json_schema = super().generate_inner(schema)
        if (
            isinstance(schema, dict)
            and schema.get("type") in ("model-field", "computed-field")
            and (json_schema.get("readOnly") or json_schema.get("deprecated"))
        ):
            raise PydanticOmit
        return json_schema


def tool_input_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Input JSON Schema for a tool: the model's schema minus read-only fields."""
    return model.model_json_schema(mode="serialization", schema_generator=ToolInputSchemaGenerator)
