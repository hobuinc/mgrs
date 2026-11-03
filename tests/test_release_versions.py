"""Keep package filenames and embedded versions tied to the Python release."""

import io
import json
import shutil
import tarfile
import tomllib

import pytest

from scripts import sync_versions


@pytest.fixture
def checkout(tmp_path):
    (tmp_path / "mgrs").mkdir()
    (tmp_path / "mgrs/__init__.py").write_text(
        'raise RuntimeError("must not import the native package")\n'
        '__version__ = "1.7.0"\n'
    )
    for filename, name in sync_versions.PACKAGES.items():
        path = tmp_path / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'[package]\nname = "{name}"\nversion = "1.6.0"\n')
    (tmp_path / "Cargo.lock").write_text(
        "version = 4\n\n"
        + "\n".join(
            f'[[package]]\nname = "{name}"\nversion = "1.6.0"\n'
            for name in ["mgrs-geotrans", "mgrs-python", "unrelated"]
        )
    )
    directory = tmp_path / "typescript"
    directory.mkdir()
    package = {"name": "mgrs-geotrans", "version": "1.6.0"}
    (directory / "package.json").write_text(json.dumps(package))
    lock = {
        **package,
        "lockfileVersion": 3,
        "packages": {
            "": package,
            "node_modules/unrelated": {"version": "1.6.0"},
        },
    }
    (directory / "package-lock.json").write_text(json.dumps(lock))
    return tmp_path


def test_synchronizes_manifests_and_lockfiles_without_importing(checkout):
    version = sync_versions.release_version(checkout, "1.7.0")
    assert version == "1.7.0"
    with pytest.raises(ValueError, match="need synchronization"):
        sync_versions.synchronize(checkout, version, check=True)
    assert len(sync_versions.synchronize(checkout, version)) == 5
    for filename in sync_versions.PACKAGES:
        metadata = tomllib.loads((checkout / filename).read_text())
        assert metadata["package"]["version"] == version
    packages = tomllib.loads((checkout / "Cargo.lock").read_text())["package"]
    assert [p["version"] for p in packages] == [version, version, "1.6.0"]
    npm = checkout / "typescript"
    assert json.loads((npm / "package.json").read_text())["version"] == version
    lock = json.loads((npm / "package-lock.json").read_text())
    assert lock["version"] == lock["packages"][""]["version"] == version
    assert lock["packages"]["node_modules/unrelated"]["version"] == "1.6.0"
    assert sync_versions.synchronize(checkout, version) == []
    assert sync_versions.synchronize(checkout, version, check=True) == []


@pytest.mark.parametrize(
    "version,expected",
    [
        ("1.7.1", "1.7.1"),
        ("1.8.0a2", "1.8.0-alpha.2"),
        ("1.8.0b3", "1.8.0-beta.3"),
        ("1.8.0rc1", "1.8.0-rc.1"),
    ],
)
def test_future_releases_and_prereleases(checkout, version, expected):
    (checkout / "mgrs/__init__.py").write_text(f'__version__ = "{version}"\n')
    assert sync_versions.release_version(checkout, "v" + version) == expected


@pytest.mark.parametrize("with_typescript", [True, False])
@pytest.mark.parametrize(
    "version,expected", [("1.7.1", "1.7.1"), ("1.8.0rc1", "1.8.0-rc.1")]
)
def test_build_metadata_syncs_checkout_and_sdist(
    checkout, monkeypatch, with_typescript, version, expected
):
    (checkout / "mgrs/__init__.py").write_text(
        'raise RuntimeError("must not import the native package")\n'
        f'__version__ = "{version}"\n'
    )
    if not with_typescript:
        shutil.rmtree(checkout / "typescript")
    monkeypatch.setattr(sync_versions, "ROOT", checkout)
    assert sync_versions.dynamic_metadata({}, {}) == {"version": version}
    assert (
        sync_versions.synchronize(
            checkout, expected, check=True, include_npm=with_typescript
        )
        == []
    )
    files = [p for p in checkout.rglob("*") if p.is_file()]
    before = {p: p.stat().st_mtime_ns for p in files}
    assert sync_versions.dynamic_metadata({}, {}) == {"version": version}
    assert all(p.stat().st_mtime_ns == stamp for p, stamp in before.items())


def test_mismatched_tag_does_not_modify_checkout(checkout, monkeypatch):
    before = {p: p.read_bytes() for p in checkout.rglob("*") if p.is_file()}
    monkeypatch.setattr(sync_versions, "ROOT", checkout)
    monkeypatch.setattr("sys.argv", ["sync_versions.py", "--tag", "1.8.0"])
    with pytest.raises(SystemExit) as error:
        sync_versions.main()
    assert error.value.code == 2
    assert all(p.read_bytes() == text for p, text in before.items())


def test_malformed_manifest_does_not_partially_update(checkout):
    path = checkout / "typescript/package-lock.json"
    path.write_text("{}")
    before = (checkout / "rust/Cargo.toml").read_bytes()
    with pytest.raises(KeyError):
        sync_versions.synchronize(checkout, "1.7.0")
    assert (checkout / "rust/Cargo.toml").read_bytes() == before


def make_archives(directory, filename_version="1.7.0", inner_version="1.7.0"):
    for extension, member, text in [
        (
            "crate",
            f"mgrs-geotrans-{filename_version}/Cargo.toml",
            f'[package]\nname="mgrs-geotrans"\nversion="{inner_version}"\n',
        ),
        (
            "tgz",
            "package/package.json",
            json.dumps({"name": "mgrs-geotrans", "version": inner_version}),
        ),
    ]:
        path = directory / f"mgrs-geotrans-{filename_version}.{extension}"
        with tarfile.open(path, "w:gz") as archive:
            data = text.encode()
            info = tarfile.TarInfo(member)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))


def test_archive_versions_and_filenames(tmp_path):
    make_archives(tmp_path)
    sync_versions.verify_artifacts(tmp_path, "1.7.0")
    make_archives(tmp_path, inner_version="1.6.0")
    with pytest.raises(ValueError, match="inside"):
        sync_versions.verify_artifacts(tmp_path, "1.7.0")


def test_old_or_missing_archives_fail_before_upload(tmp_path):
    with pytest.raises(ValueError, match="Expected only"):
        sync_versions.verify_artifacts(tmp_path, "1.7.0")
    make_archives(tmp_path, filename_version="1.6.0", inner_version="1.6.0")
    with pytest.raises(ValueError, match="Expected only"):
        sync_versions.verify_artifacts(tmp_path, "1.7.0")
    make_archives(tmp_path)
    with pytest.raises(ValueError, match="Expected only"):
        sync_versions.verify_artifacts(tmp_path, "1.7.0")
