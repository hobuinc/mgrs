"""Keep native benchmark builds isolated without copying source files."""

import zipfile
from types import SimpleNamespace

import pytest

from benchmarks import build
from benchmarks.performance import native_library


def test_extracts_only_native_artifacts(tmp_path):
    wheel = tmp_path / "mgrs.whl"
    source = tmp_path / "checkout"
    source.mkdir()
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("mgrs/_native.test.so", b"extension")
        archive.writestr("mgrs/__init__.py", "do not overwrite source")
        archive.writestr("mgrs.dist-info/METADATA", "metadata")
    output = build.unpack_native(wheel, source)
    assert output == [source / "mgrs" / "_native.test.so"]
    assert output[0].read_bytes() == b"extension"
    assert not (source / "mgrs" / "__init__.py").exists()


@pytest.mark.parametrize("member", ["../outside.so", "/absolute.so"])
def test_rejects_unsafe_wheel_paths(tmp_path, member):
    wheel = tmp_path / "mgrs.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(member, b"extension")
    with pytest.raises(ValueError, match="unsafe"):
        build.unpack_native(wheel, tmp_path / "source")


def test_native_binary_identity_supports_both_backends():
    handle = SimpleNamespace(_name="old.so")
    old = SimpleNamespace(core=SimpleNamespace(rt=handle))
    new = SimpleNamespace(_native=SimpleNamespace(__file__="new.so"))
    assert native_library(old) == "old.so"
    assert native_library(new) == "new.so"
