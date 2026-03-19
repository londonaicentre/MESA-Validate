"""
export_schema.py - Export Pydantic schemas to JSON Schema with pre-computed metadata

Generates a JSON file containing:
- Standard JSON Schema from model_json_schema()
- Pre-computed metadata for the web validation tool (class paths, list items, enum containers, etc.)

Usage:
    python tools/export_schema.py
    python tools/export_schema.py --output path/to/output.json
"""

import argparse
import importlib
import inspect
import json
import sys
from enum import Enum
from pathlib import Path
from typing import get_args, get_origin

import yaml
from pydantic import BaseModel


def load_schemas_config(config_path="schemas.yaml"):
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    return config.get("schemas", [])


def extract_all_classes(module):
    classes = {}
    for name, obj in inspect.getmembers(module, inspect.isclass):
        if obj is BaseModel or obj is Enum:
            continue
        if isinstance(obj, type) and issubclass(obj, BaseModel):
            classes[name] = {
                "type": "BaseModel",
                "class": obj,
                "fields": get_fields_from_class(obj),
            }
        elif isinstance(obj, type) and issubclass(obj, Enum):
            classes[name] = {
                "type": "Enum",
                "class": obj,
                "values": [e.value for e in obj],
            }
    return classes


def get_fields_from_class(class_obj):
    if not isinstance(class_obj, type) or not issubclass(class_obj, BaseModel):
        return {}
    fields = {}
    for field_name, field_info in class_obj.model_fields.items():
        field_type = field_info.annotation
        origin = get_origin(field_type)
        if str(origin) == "typing.Union":
            args = get_args(field_type)
            field_type = next((a for a in args if a is not type(None)), field_type)
            origin = get_origin(field_type)
        is_list = origin is list
        is_enum = isinstance(field_type, type) and issubclass(field_type, Enum)
        is_basemodel = isinstance(field_type, type) and issubclass(field_type, BaseModel)
        fields[field_name] = {
            "type": str(field_type.__name__) if hasattr(field_type, "__name__") else str(field_type),
            "is_list": is_list,
            "is_enum": is_enum,
            "is_basemodel": is_basemodel,
        }
    return fields


def is_class_used_as_list_item(classes, target_class_name):
    for _, class_info in classes.items():
        if class_info["type"] != "BaseModel":
            continue
        basemodel_class = class_info["class"]
        for _, field_info in basemodel_class.model_fields.items():
            annotation = field_info.annotation
            origin = get_origin(annotation)
            if str(origin) == "typing.Union":
                args = get_args(annotation)
                for arg in args:
                    if arg is not type(None):
                        annotation = arg
                        break
            origin = get_origin(annotation)
            if origin is list:
                args = get_args(annotation)
                if args and hasattr(args[0], "__name__") and args[0].__name__ == target_class_name:
                    return True
    return False


def find_class_path_recursive(root_class, target_class_name, path):
    for field_name, field_info in root_class.model_fields.items():
        annotation = field_info.annotation
        origin = get_origin(annotation)
        actual_types = []
        if origin is list:
            args = get_args(annotation)
            if args:
                actual_types.append(args[0])
        elif str(origin) == "typing.Union":
            args = get_args(annotation)
            for arg in args:
                if arg is not type(None):
                    inner_origin = get_origin(arg)
                    if inner_origin is list:
                        inner_args = get_args(arg)
                        if inner_args:
                            actual_types.append(inner_args[0])
                    else:
                        actual_types.append(arg)
        else:
            actual_types.append(annotation)
        for actual_type in actual_types:
            if hasattr(actual_type, "__name__") and actual_type.__name__ == target_class_name:
                return path + [field_name]
            if hasattr(actual_type, "model_fields"):
                result = find_class_path_recursive(actual_type, target_class_name, path + [field_name])
                if result:
                    return result
    return None


def find_enum_containers(classes, enum_class_name):
    enum_info = classes.get(enum_class_name)
    if not enum_info or enum_info["type"] != "Enum":
        return []
    enum_class = enum_info["class"]
    containers = []
    for class_name, class_info in classes.items():
        if class_info["type"] != "BaseModel":
            continue
        basemodel_class = class_info["class"]
        for field_name, field_info in basemodel_class.model_fields.items():
            annotation = field_info.annotation
            origin = get_origin(annotation)
            if str(origin) == "typing.Union":
                args = get_args(annotation)
                for arg in args:
                    if arg is not type(None):
                        annotation = arg
                        break
            if annotation == enum_class:
                containers.append([class_name, field_name])
    return containers


def export_schema(schema_config):
    module_name = schema_config["module"]
    root_class_name = schema_config["root_class"]

    module = importlib.import_module(module_name)
    root_class = getattr(module, root_class_name)

    json_schema = root_class.model_json_schema()
    classes = extract_all_classes(module)

    # Build serializable classes metadata (without Python class objects)
    classes_meta = {}
    for name, info in classes.items():
        entry = {"type": info["type"]}
        if info["type"] == "BaseModel":
            entry["fields"] = info["fields"]
        elif info["type"] == "Enum":
            entry["values"] = info["values"]
        classes_meta[name] = entry

    # Pre-compute list item classes
    list_item_classes = [
        name for name in classes if classes[name]["type"] == "BaseModel" and is_class_used_as_list_item(classes, name)
    ]

    # Pre-compute class paths
    class_paths = {}
    for name in classes:
        path = find_class_path_recursive(root_class, name, [])
        if path:
            class_paths[name] = path

    # Pre-compute enum containers
    enum_containers = {}
    for name, info in classes.items():
        if info["type"] == "Enum":
            containers = find_enum_containers(classes, name)
            if containers:
                enum_containers[name] = containers

    # Pre-compute which enums are used in list context
    enums_in_list_context = []
    for name, info in classes.items():
        if info["type"] != "Enum":
            continue
        containers = enum_containers.get(name, [])
        if containers and all(c[0] in list_item_classes for c in containers):
            enums_in_list_context.append(name)

    return {
        "schema_name": module_name,
        "root_class": root_class_name,
        "json_schema": json_schema,
        "_mesa_metadata": {
            "classes": classes_meta,
            "list_item_classes": list_item_classes,
            "class_paths": class_paths,
            "enum_containers": enum_containers,
            "enums_in_list_context": enums_in_list_context,
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Export Pydantic schemas to JSON Schema with metadata")
    parser.add_argument("--config", default="schemas.yaml", help="Path to schemas.yaml")
    parser.add_argument("--output", default=None, help="Output directory (default: mesa-validate-web/schemas/)")
    args = parser.parse_args()

    schemas = load_schemas_config(args.config)
    if not schemas:
        print("No schemas found in config")
        sys.exit(1)

    output_dir = Path(args.output) if args.output else Path("mesa-validate-web/schemas")
    output_dir.mkdir(parents=True, exist_ok=True)

    for schema_config in schemas:
        print(f"Exporting {schema_config['module']}...")
        result = export_schema(schema_config)
        output_path = output_dir / f"{schema_config['module']}.schema.json"
        with open(output_path, "w") as f:
            json.dump(result, f, indent=2)
        print(f"  -> {output_path}")
        print(f"  Classes: {len(result['_mesa_metadata']['classes'])}")
        print(f"  List item classes: {result['_mesa_metadata']['list_item_classes']}")
        print(f"  Enums in list context: {result['_mesa_metadata']['enums_in_list_context']}")

    print("Done!")


if __name__ == "__main__":
    main()
