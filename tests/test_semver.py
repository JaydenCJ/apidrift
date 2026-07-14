"""Semver arithmetic: parsing, bump suggestion, the pre-1.0 remap, check."""

import pytest

from apidrift.rules import Change
from apidrift.semver import (
    VersionError,
    actual_bump,
    is_sufficient,
    next_version,
    parse_version,
    read_project_version,
    required_bump,
    required_bump_for,
)


def _changes(*kinds: str):
    return [Change(kind, "p.x", "test change") for kind in kinds]


def test_parse_version_handles_common_spellings_and_rejects_garbage():
    assert parse_version("1.2.3") == (1, 2, 3)
    assert parse_version("v2.0.0") == (2, 0, 0)
    assert parse_version("1.4") == (1, 4, 0)
    assert parse_version("1.2.3rc1") == (1, 2, 3)
    assert parse_version("1.2.3-beta.2") == (1, 2, 3)
    with pytest.raises(VersionError):
        parse_version("latest")
    with pytest.raises(VersionError):
        parse_version("")


def test_required_bump_takes_the_worst_severity():
    assert required_bump(_changes("function-added", "function-removed")) == "major"
    assert required_bump(_changes("function-added", "annotation-changed")) == "minor"
    assert required_bump(_changes("annotation-changed")) == "patch"
    assert required_bump([]) == "none"


def test_pre_1_0_remap_downshifts_major_and_minor():
    breaking = _changes("function-removed")
    additive = _changes("function-added")
    assert required_bump_for(breaking, "0.4.2") == "minor"
    assert required_bump_for(additive, "0.4.2") == "patch"
    assert required_bump_for(breaking, "1.4.2") == "major"
    assert required_bump_for(breaking, None) == "major"


def test_next_version_for_each_bump():
    assert next_version("1.4.2", "major") == "2.0.0"
    assert next_version("1.4.2", "minor") == "1.5.0"
    assert next_version("1.4.2", "patch") == "1.4.3"
    assert next_version("1.4.2", "none") == "1.4.2"


def test_actual_bump_detects_the_stepped_position_and_rejects_rollbacks():
    assert actual_bump("1.4.2", "2.0.0") == "major"
    assert actual_bump("1.4.2", "1.5.0") == "minor"
    assert actual_bump("1.4.2", "1.4.3") == "patch"
    assert actual_bump("1.4.2", "1.4.2") == "none"
    with pytest.raises(VersionError, match="backwards"):
        actual_bump("2.0.0", "1.9.9")


def test_is_sufficient_compares_declared_step_to_required():
    breaking = _changes("function-removed")
    assert is_sufficient("1.0.0", "2.0.0", breaking)
    assert not is_sufficient("1.0.0", "1.1.0", breaking)
    # Over-bumping is allowed: a major release may contain only additions.
    assert is_sufficient("1.0.0", "2.0.0", _changes("function-added"))
    # Pre-1.0: breaking only requires a minor step.
    assert is_sufficient("0.3.0", "0.4.0", breaking)
    assert not is_sufficient("0.3.0", "0.3.1", breaking)


def test_read_project_version_reads_only_the_project_table():
    text = (
        "[build-system]\nrequires = []\n\n"
        '[project]\nname = "x"\nversion = "3.1.4"\n\n'
        '[tool.other]\nversion = "9.9.9"\n'
    )
    assert read_project_version(text) == "3.1.4"
    assert read_project_version('[tool.poetry]\nversion = "1.0.0"\n') is None
    assert (
        read_project_version('[project]\nname = "x"\ndynamic = ["version"]\n')
        is None
    )
