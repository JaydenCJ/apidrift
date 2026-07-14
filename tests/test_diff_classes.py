"""Class-level diff rules: methods, bases, properties, enums, attributes."""

from conftest import diff_src, kinds


def test_method_removal_is_major_addition_is_minor():
    removed = diff_src(
        "class C:\n    def a(self): pass\n    def b(self): pass",
        "class C:\n    def a(self): pass",
    )
    added = diff_src(
        "class C:\n    def a(self): pass",
        "class C:\n    def a(self): pass\n    def b(self): pass",
    )
    assert kinds(removed) == ["method-removed"]
    assert removed[0].severity == "major"
    assert removed[0].symbol == "m.C.b"
    assert kinds(added) == ["method-added"]
    assert added[0].severity == "minor"


def test_base_class_removal_is_major_addition_is_minor():
    removed = diff_src("class C(Base): pass", "class C: pass")
    added = diff_src("class C: pass", "class C(Mixin): pass")
    assert kinds(removed) == ["base-removed"]
    assert removed[0].severity == "major"  # isinstance checks can break
    assert kinds(added) == ["base-added"]
    assert added[0].severity == "minor"


def test_property_turned_into_method_is_major():
    changes = diff_src(
        """
        class C:
            @property
            def size(self): return 0
        """,
        """
        class C:
            def size(self): return 0
        """,
    )
    assert kinds(changes) == ["role-changed"]
    assert changes[0].severity == "major"
    assert changes[0].old == "property" and changes[0].new == "method"


def test_role_change_suppresses_signature_noise():
    # property -> classmethod also changes the parameter list; only the role
    # change should be reported because the signatures are incomparable.
    changes = diff_src(
        """
        class C:
            @property
            def size(self): return 0
        """,
        """
        class C:
            @classmethod
            def size(cls, unit): return 0
        """,
    )
    assert kinds(changes) == ["role-changed"]


def test_property_setter_added_is_minor_removed_is_major():
    getter_only = """
        class C:
            @property
            def size(self): return self._s
        """
    with_setter = """
        class C:
            @property
            def size(self): return self._s
            @size.setter
            def size(self, value): self._s = value
        """
    added = diff_src(getter_only, with_setter)
    removed = diff_src(with_setter, getter_only)
    assert kinds(added) == ["property-setter-added"]
    assert added[0].severity == "minor"  # ``c.size = v`` starts working
    assert kinds(removed) == ["property-setter-removed"]
    assert removed[0].severity == "major"  # ``c.size = v`` stops working


def test_property_accessor_defs_never_produce_signature_noise():
    # The setter's ``value`` parameter and a deleter def are implementation
    # plumbing — a property has no caller-facing call signature, so neither
    # may surface as a (false) param or role change.
    changes = diff_src(
        """
        class C:
            @property
            def size(self): return self._s
        """,
        """
        class C:
            @property
            def size(self): return self._s
            @size.deleter
            def size(self): del self._s
        """,
    )
    assert changes == []


def test_init_signature_changes_are_tracked():
    changes = diff_src(
        "class C:\n    def __init__(self, a): pass",
        "class C:\n    def __init__(self, a, b): pass",
    )
    assert kinds(changes) == ["param-added-required"]
    assert changes[0].symbol == "m.C.__init__"


def test_enum_member_removal_is_major_addition_is_minor():
    v1 = """
        from enum import Enum
        class Color(Enum):
            RED = 1
            BLUE = 2
        """
    v2 = """
        from enum import Enum
        class Color(Enum):
            RED = 1
        """
    removed = diff_src(v1, v2)
    added = diff_src(v2, v1)
    assert kinds(removed) == ["enum-member-removed"]
    assert "enum member" in removed[0].message
    assert kinds(added) == ["enum-member-added"]
    assert added[0].severity == "minor"


def test_class_attribute_severities_removal_addition_value_change():
    removed = diff_src("class C:\n    A = 1\n    B = 2", "class C:\n    A = 1")
    added = diff_src("class C:\n    A = 1", "class C:\n    A = 1\n    B = 2")
    changed = diff_src("class C:\n    LIMIT = 10", "class C:\n    LIMIT = 20")
    assert kinds(removed) == ["attribute-removed"]
    assert removed[0].severity == "major"
    assert kinds(added) == ["attribute-added"]
    assert added[0].severity == "minor"
    assert kinds(changed) == ["variable-value-changed"]
    assert changed[0].severity == "patch"


def test_abstractness_flips_major_when_gained_minor_when_lost():
    concrete = """
        import abc
        class C(abc.ABC):
            def run(self): pass
        """
    abstract = """
        import abc
        class C(abc.ABC):
            @abc.abstractmethod
            def run(self): pass
        """
    became_abstract = diff_src(concrete, abstract)
    became_concrete = diff_src(abstract, concrete)
    assert kinds(became_abstract) == ["method-became-abstract"]
    assert became_abstract[0].severity == "major"  # subclasses stop instantiating
    assert kinds(became_concrete) == ["method-became-concrete"]
    assert became_concrete[0].severity == "minor"
