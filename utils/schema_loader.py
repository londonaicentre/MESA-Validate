"""
schema_loader.py - Schema configuration loading from YAML

Reads schemas.yaml configuration file to discover available schemas for validation
Schemas are Python packages (installed via requirements.txt) that define Pydantic models
Defines root_class which is top-level Pydantic model as entry point for schema traversal
"""

from pathlib import Path

import yaml


def load_schemas_config(config_path="schemas.yaml"):
    """
    Load schemas configuration from YAML file
    """
    config_file = Path(config_path)

    if not config_file.exists():
        return []

    try:
        with open(config_file, "r") as f:
            config = yaml.safe_load(f)
            schemas_raw = config.get("schemas", [])

            schemas = []
            for item in schemas_raw:
                if not isinstance(item, dict):
                    raise ValueError(f"Schema must be dict with 'module' and 'root_class': {item}")
                if "root_class" not in item:
                    raise ValueError(f"Schema missing required 'root_class': {item}")
                schemas.append({"module": item["module"], "root_class": item["root_class"]})

            return schemas
    except Exception as e:
        raise Exception(f"Failed to load schemas config: {e}")


def get_schema_list():
    """
    Get list of available schemas from YAML config
    """
    schema_configs = load_schemas_config()

    schemas = []
    for config in schema_configs:
        schemas.append({
            "module": config["module"],
            "name": config["module"],  # use module name as display name
            "root_class": config.get("root_class")
        })

    return schemas
