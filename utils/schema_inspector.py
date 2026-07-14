"""
schema_inspector.py - Schema introspection to match items to validation approach

Analyses Pydantic schema structure to determine how to validate predictions
Module name and root_class from schema_loader.py
The inspector discovers all classes (BaseModel and Enum) in a schema module
Recursively traverses schema hierarchy to find class locations, and determines validation type (binary vs list)
"""

import importlib
import inspect
from enum import Enum
from typing import get_args, get_origin

from pydantic import BaseModel


class SchemaInspector:
    """
    Inspector for schema module with cached introspection
    """

    def __init__(self, module_name, root_class_name):
        """
        Initialise schema inspector

        Args:
            module_name:
                Module import path (e.g., "oncollamaschemav3")
            root_class_name:
                Root class name from config
        """
        self.module_name = module_name
        self.module = self._load_module(module_name)
        self.root_class = self._get_root_class(root_class_name)
        self._classes_cache = None

    @property
    def classes(self):
        """
        Lazy-loaded cache of all classes in module

        Returns:
            Dict with class_name as key and metadata as value:
            {
                "ClassName": {
                    "type": "BaseModel" | "Enum",
                    "class": class_obj,
                    "fields": {...}  # For BaseModel
                    "values": [...]  # For Enum
                }
            }
        """
        if self._classes_cache is None:
            self._classes_cache = self._extract_all_classes()
        return self._classes_cache

    def get_class_fields(self, class_name):
        """
        Get fields for a specific class

        Args:
            class_name: Name of the class

        Returns:
            Dict of field metadata:
            {
                "field_name": {
                    "type": "TypeName",
                    "is_list": bool,
                    "is_enum": bool,
                    "is_basemodel": bool
                }
            }
        """
        class_info = self.classes.get(class_name)
        if not class_info or class_info["type"] != "BaseModel":
            return {}

        class_obj = class_info["class"]
        return self._get_fields_from_class(class_obj)

    def find_class_path(self, target_class_name, path=None):
        """
        Recursively find a class in Pydantic model fields

        Args:
            target_class_name:
                Name of class to find
            path:
                Current path (used in recursion)

        Returns:
            List of field names forming path to target class
            Example: ['primary_cancer', 'primary_cancer_facts']
        """
        if path is None:
            path = []

        if self.root_class is None:
            return None

        # The root class is not a field of itself; its data lives at the top of
        # the extraction dict, so its path is empty (not None = "not found").
        if target_class_name == self.root_class.__name__:
            return list(path)

        return self._find_class_path_recursive(self.root_class, target_class_name, path)

    def find_enum_containers(self, enum_class_name):
        """
        Find all BaseModel classes containing this enum

        Args:
            enum_class_name:
                Name of enum class

        Returns:
            List of (class_name, field_name) tuples
        """
        enum_info = self.classes.get(enum_class_name)
        if not enum_info or enum_info["type"] != "Enum":
            return []

        enum_class = enum_info["class"]
        containers = []

        for class_name, class_info in self.classes.items():
            if class_info["type"] != "BaseModel":
                continue

            basemodel_class = class_info["class"]
            enum_field = self._find_enum_field_name(basemodel_class, enum_class)

            if enum_field:
                containers.append((class_name, enum_field))

        return containers

    def is_class_used_as_list_item(self, target_class_name):
        """
        Check if class is used as List[ClassName] anywhere in schema

        Args:
            target_class_name:
                Name of class to check

        Returns:
            True if class appears as List[ClassName] in any field
        """
        for _, class_info in self.classes.items():
            if class_info["type"] != "BaseModel":
                continue

            basemodel_class = class_info["class"]

            for _, field_info in basemodel_class.model_fields.items():
                annotation = field_info.annotation

                # unwrap Union
                origin = get_origin(annotation)
                if str(origin) == "typing.Union":
                    args = get_args(annotation)
                    for arg in args:
                        if arg is not type(None):
                            annotation = arg
                            break

                # check if it's a list
                origin = get_origin(annotation)
                if origin is list:
                    args = get_args(annotation)
                    if args:
                        list_item_type = args[0]
                        if (
                            hasattr(list_item_type, "__name__")
                            and list_item_type.__name__ == target_class_name
                        ):
                            return True

        return False

    def is_enum_used_in_list_context(self, enum_class_name):
        """
        Check if enum is used ONLY in list contexts

        An enum is in list context if:
        - It's a field in a BaseModel class AND
        - That BaseModel class is used as List[ClassName] somewhere
        - ALL container classes are used as list items

        Args:
            enum_class_name:
                Name of enum class

        Returns:
            True only if ALL containers of this enum are used as list items
        """
        containers = self.find_enum_containers(enum_class_name)

        if not containers:
            return False

        for container_class_name, _ in containers:
            if not self.is_class_used_as_list_item(container_class_name):
                return False

        return True

    def find_enum_field_name(self, basemodel_class_name, enum_class_name):
        """
        Find field name in BaseModel that uses this enum

        Args:
            basemodel_class_name:
                Name of BaseModel class
            enum_class_name:
                Name of enum class

        Returns:
            Field name or None
        """
        basemodel_info = self.classes.get(basemodel_class_name)
        enum_info = self.classes.get(enum_class_name)

        if (
            not basemodel_info
            or basemodel_info["type"] != "BaseModel"
            or not enum_info
            or enum_info["type"] != "Enum"
        ):
            return None

        basemodel_class = basemodel_info["class"]
        enum_class = enum_info["class"]

        return self._find_enum_field_name(basemodel_class, enum_class)

    def _load_module(self, module_name):
        """
        Import schema module
        """
        try:
            module = importlib.import_module(module_name)
            return module
        except ImportError as e:
            raise ImportError(f"Could not import schema module '{module_name}': {e}")

    def _get_root_class(self, root_class_name):
        """
        Get root schema class
        """
        if not hasattr(self.module, root_class_name):
            raise ValueError(
                f"Root class '{root_class_name}' not found in '{self.module_name}'"
            )
        return getattr(self.module, root_class_name)

    def _extract_all_classes(self):
        """
        Extract all BaseModel and Enum classes from module

        Returns:
            Dict with class_name as key and metadata as value
        """
        classes = {}

        for name, obj in inspect.getmembers(self.module, inspect.isclass):
            if obj is BaseModel or obj is Enum:
                continue

            if isinstance(obj, type) and issubclass(obj, BaseModel):
                classes[name] = {
                    "type": "BaseModel",
                    "class": obj,
                    "fields": self._get_fields_from_class(obj),
                }

            elif isinstance(obj, type) and issubclass(obj, Enum):
                classes[name] = {
                    "type": "Enum",
                    "class": obj,
                    "values": [e.value for e in obj],
                }

        return classes

    def _get_fields_from_class(self, class_obj):
        """
        Get fields from a BaseModel class
        """
        if not isinstance(class_obj, type) or not issubclass(class_obj, BaseModel):
            return {}

        fields = {}

        for field_name, field_info in class_obj.model_fields.items():
            field_type = field_info.annotation
            origin = get_origin(field_type)

            # unwrap Optional
            if str(origin) == "typing.Union":
                args = get_args(field_type)
                field_type = next((a for a in args if a is not type(None)), field_type)
                origin = get_origin(field_type)

            is_list = origin is list
            is_enum = isinstance(field_type, type) and issubclass(field_type, Enum)
            is_basemodel = isinstance(field_type, type) and issubclass(
                field_type, BaseModel
            )

            fields[field_name] = {
                "type": str(field_type.__name__)
                if hasattr(field_type, "__name__")
                else str(field_type),
                "is_list": is_list,
                "is_enum": is_enum,
                "is_basemodel": is_basemodel,
            }

        return fields

    def _find_class_path_recursive(self, root_class, target_class_name, path):
        """
        Recursively search for a class in the model hierarchy

        Args:
            root_class:
                Current class to search in
            target_class_name:
                Name of class to find
            path:
                Current path

        Returns:
            Path to target class or None
        """
        for field_name, field_info in root_class.model_fields.items():
            annotation = field_info.annotation

            # unwrap optional[x] and list[x] wrappers
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
                if (
                    hasattr(actual_type, "__name__")
                    and actual_type.__name__ == target_class_name
                ):
                    return path + [field_name]

                if hasattr(actual_type, "model_fields"):
                    result = self._find_class_path_recursive(
                        actual_type, target_class_name, path + [field_name]
                    )
                    if result:
                        return result

        return None

    def _find_enum_field_name(self, basemodel_class, enum_class):
        """
        Find field name in BaseModel that uses specific enum type

        Args:
            basemodel_class:
                BaseModel class
            enum_class:
                Enum class

        Returns:
            Field name or None
        """
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
                return field_name

        return None
