"""Utility functions for yaml2helm."""

from typing import Any, Dict, List
import re


def normalize_dict(obj: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively sort dictionary keys for deterministic output."""
    if not isinstance(obj, dict):
        return obj

    result = {}
    for key in sorted(obj.keys()):
        value = obj[key]
        if isinstance(value, dict):
            result[key] = normalize_dict(value)
        elif isinstance(value, list):
            result[key] = normalize_list(value)
        else:
            result[key] = value
    return result


def normalize_list(items: List[Any]) -> List[Any]:
    """Recursively normalize list items."""
    result = []
    for item in items:
        if isinstance(item, dict):
            result.append(normalize_dict(item))
        elif isinstance(item, list):
            result.append(normalize_list(item))
        else:
            result.append(item)
    return result


def sanitize_name(name: str) -> str:
    """Sanitize a name for use in filenames and Helm."""
    # Replace non-alphanumeric characters with hyphens
    sanitized = re.sub(r'[^a-z0-9-]', '-', name.lower())
    # Remove duplicate hyphens
    sanitized = re.sub(r'-+', '-', sanitized)
    # Strip leading/trailing hyphens
    return sanitized.strip('-')


def get_nested_value(obj: Dict[str, Any], path: str, default: Any = None) -> Any:
    """Get a nested value from a dictionary using dot notation.

    Example: get_nested_value(obj, 'spec.replicas') -> obj['spec']['replicas']
    """
    keys = path.split('.')
    current = obj

    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default

    return current


def set_nested_value(obj: Dict[str, Any], path: str, value: Any) -> None:
    """Set a nested value in a dictionary using dot notation.

    Example: set_nested_value(obj, 'spec.replicas', '{{ .Values.replicas }}')
    """
    keys = path.split('.')
    current = obj

    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        current = current[key]

    current[keys[-1]] = value


def is_k8s_resource(obj: Any) -> bool:
    """Check if an object looks like a valid Kubernetes resource."""
    if not isinstance(obj, dict):
        return False

    required_fields = ['apiVersion', 'kind', 'metadata']
    if not all(field in obj for field in required_fields):
        return False

    if not isinstance(obj.get('metadata'), dict):
        return False

    if 'name' not in obj['metadata']:
        return False

    return True


def get_resource_identifier(obj: Dict[str, Any]) -> str:
    """Get a unique identifier for a Kubernetes resource."""
    kind = obj.get('kind', 'unknown')
    name = obj.get('metadata', {}).get('name', 'unnamed')
    return f"{kind.lower()}-{sanitize_name(name)}"
