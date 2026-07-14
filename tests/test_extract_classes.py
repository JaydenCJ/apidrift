"""Extraction of classes: methods, roles, attributes, enums, dataclasses."""

from apidrift.model import (
    ROLE_CLASSMETHOD,
    ROLE_METHOD,
    ROLE_PROPERTY,
    ROLE_STATICMETHOD,
)

from conftest import extract_src


def test_methods_bases_and_async_flags_are_recorded():
    mod = extract_src(
        """
        class Client(BaseClient, dict):
            def fetch(self, url): pass
            async def stream(self): pass
        """
    )
    cls = mod.classes["Client"]
    assert cls.bases == ["BaseClient", "dict"]
    assert cls.methods["fetch"].role == ROLE_METHOD
    assert cls.methods["stream"].is_async


def test_decorator_roles_property_classmethod_staticmethod():
    mod = extract_src(
        """
        import functools

        class C:
            @property
            def size(self): return 0
            @functools.cached_property
            def cached(self): return 0
            @classmethod
            def build(cls): pass
            @staticmethod
            def helper(): pass
        """
    )
    cls = mod.classes["C"]
    assert cls.methods["size"].role == ROLE_PROPERTY
    assert cls.methods["cached"].role == ROLE_PROPERTY
    assert cls.methods["build"].role == ROLE_CLASSMETHOD
    assert cls.methods["helper"].role == ROLE_STATICMETHOD


def test_property_setter_stays_a_property():
    mod = extract_src(
        """
        class C:
            @property
            def size(self): return self._s
            @size.setter
            def size(self, value): self._s = value
        """
    )
    prop = mod.classes["C"].methods["size"]
    assert prop.role == ROLE_PROPERTY
    assert prop.has_setter
    # The getter stays the canonical record: the setter's ``value``
    # parameter must not leak into the property's recorded signature.
    assert [p.name for p in prop.params] == ["self"]


def test_property_deleter_stays_a_property():
    mod = extract_src(
        """
        class C:
            @property
            def size(self): return self._s
            @size.deleter
            def size(self): del self._s
        """
    )
    prop = mod.classes["C"].methods["size"]
    assert prop.role == ROLE_PROPERTY
    assert not prop.has_setter  # a deleter alone does not make it writable


def test_dunder_methods_are_api_but_dunder_attributes_are_not():
    mod = extract_src(
        """
        class C:
            __slots__ = ("a",)
            LIMIT = 10
            def __init__(self, a): pass
            def __call__(self, b): pass
            def _internal(self): pass
        """
    )
    cls = mod.classes["C"]
    assert set(cls.methods) == {"__init__", "__call__"}
    assert set(cls.attributes) == {"LIMIT"}


def test_class_attributes_capture_literal_values_and_annotations():
    mod = extract_src(
        """
        class C:
            LIMIT: int = 10
            NAME = "c"
            computed = compute()
        """
    )
    attrs = mod.classes["C"].attributes
    assert attrs["LIMIT"].annotation == "int"
    assert attrs["LIMIT"].value == "10"
    assert attrs["NAME"].value == "'c'"
    assert attrs["computed"].value is None  # opaque, never diffed by value


def test_enum_classes_are_flagged_with_members():
    mod = extract_src(
        """
        import enum

        class Color(enum.Enum):
            RED = 1
            BLUE = 2
        """
    )
    cls = mod.classes["Color"]
    assert cls.is_enum
    assert set(cls.attributes) == {"RED", "BLUE"}


def test_dataclass_decorator_is_flagged():
    mod = extract_src(
        """
        from dataclasses import dataclass

        @dataclass(frozen=True)
        class Point:
            x: int
            y: int = 0
        """
    )
    cls = mod.classes["Point"]
    assert cls.is_dataclass
    assert cls.attributes["y"].value == "0"


def test_abstract_methods_are_flagged():
    mod = extract_src(
        """
        import abc

        class Base(abc.ABC):
            @abc.abstractmethod
            def run(self): ...
        """
    )
    assert mod.classes["Base"].methods["run"].is_abstract


def test_privacy_inside_classes_and_nested_class_handling():
    mod = extract_src(
        """
        class _Hidden: pass
        class Shown:
            def _helper(self): pass
            class Config:
                pass
        """
    )
    assert set(mod.classes) == {"Shown"}
    assert mod.classes["Shown"].methods == {}
    # A nested public class is kept as an opaque attribute so its removal
    # is still caught.
    assert "Config" in mod.classes["Shown"].attributes
