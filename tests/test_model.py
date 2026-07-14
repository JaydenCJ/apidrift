"""Model serialization: dump snapshots must round-trip losslessly."""

import textwrap

import pytest

from apidrift.diffing import diff_packages
from apidrift.extract import extract_package
from apidrift.model import FORMAT_VERSION, Package


SOURCE = {
    "p": "from .core import Client\nVERSION = '1.0'",
    "p.core": textwrap.dedent(
        """
        class Client:
            LIMIT: int = 10

            def __init__(self, host, *, timeout=30.0):
                pass

            @property
            def closed(self): return self._closed

            @closed.setter
            def closed(self, value): self._closed = value

        async def ping(host: str, /) -> bool: ...
        """
    ),
}


def _pkg():
    return extract_package(SOURCE, "p", init_modules={"p"})


def test_roundtrip_through_dict_is_lossless_and_deterministic():
    pkg = _pkg()
    restored = Package.from_dict(pkg.to_dict())
    assert diff_packages(pkg, restored) == []
    assert diff_packages(restored, pkg) == []
    assert _pkg().to_dict() == _pkg().to_dict()


def test_roundtrip_preserves_signature_details():
    restored = Package.from_dict(_pkg().to_dict())
    init = restored.modules["p.core"].classes["Client"].methods["__init__"]
    timeout = [p for p in init.params if p.name == "timeout"][0]
    assert timeout.kind == "keyword-only"
    assert timeout.default == "30.0"
    ping = restored.modules["p.core"].functions["ping"]
    assert ping.is_async
    assert ping.params[0].kind == "positional-only"
    assert ping.returns == "bool"
    closed = restored.modules["p.core"].classes["Client"].methods["closed"]
    assert closed.role == "property"
    assert closed.has_setter  # setter presence survives the round-trip


def test_format_version_is_written_and_enforced():
    data = _pkg().to_dict()
    assert data["format_version"] == FORMAT_VERSION
    assert data["package"] == "p"
    data["format_version"] = 999
    with pytest.raises(ValueError, match="format_version"):
        Package.from_dict(data)


def test_reexports_and_variables_survive_the_roundtrip():
    restored = Package.from_dict(_pkg().to_dict())
    assert restored.modules["p"].reexports == {"Client": ".core:Client"}
    assert restored.modules["p"].variables["VERSION"].value == "'1.0'"
