"""JSON Schema generation for Helm values."""

import json
from typing import Any, Dict


class SchemaGenerator:
    """Generate JSON Schema for values.yaml."""

    def generate(self, values: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a JSON Schema from values dictionary.

        Args:
            values: Values dictionary

        Returns:
            JSON Schema dictionary
        """
        schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {},
            "required": []
        }

        schema["properties"] = self._infer_properties(values)

        return schema

    def _infer_properties(self, obj: Any) -> Dict[str, Any]:
        """Recursively infer JSON Schema properties from a value.

        Args:
            obj: Value to infer schema from

        Returns:
            JSON Schema properties dictionary
        """
        if isinstance(obj, dict):
            properties = {}
            for key, value in obj.items():
                properties[key] = self._infer_type(value)
            return properties
        else:
            return {}

    def _infer_type(self, value: Any) -> Dict[str, Any]:
        """Infer JSON Schema type from a Python value.

        Args:
            value: Value to infer type from

        Returns:
            JSON Schema type definition
        """
        if isinstance(value, bool):
            return {"type": "boolean"}
        elif isinstance(value, int):
            return {"type": "integer"}
        elif isinstance(value, float):
            return {"type": "number"}
        elif isinstance(value, str):
            return {"type": "string"}
        elif isinstance(value, list):
            if len(value) > 0:
                # Infer from first item
                item_type = self._infer_type(value[0])
                return {
                    "type": "array",
                    "items": item_type
                }
            else:
                return {
                    "type": "array",
                    "items": {}
                }
        elif isinstance(value, dict):
            return {
                "type": "object",
                "properties": self._infer_properties(value)
            }
        else:
            # Null or unknown type
            return {"type": "null"}

    def write_schema(self, values: Dict[str, Any], output_path: str) -> None:
        """Generate and write JSON Schema to file.

        Args:
            values: Values dictionary
            output_path: Path to write schema file
        """
        schema = self.generate(values)

        with open(output_path, 'w') as f:
            json.dump(schema, f, indent=2)
