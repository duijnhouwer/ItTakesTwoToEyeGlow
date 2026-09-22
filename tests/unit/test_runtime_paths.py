from pathlib import Path
from eyeglow_egobody import runtime_paths


def test_source_root():
    assert (runtime_paths.project_root() / 'pyproject.toml').is_file()


def test_frozen_root_uses_executable_not_internal_module(monkeypatch,tmp_path):
    executable = tmp_path/'code-repo/dist/ItTakesTwoToEyeGlow/ItTakesTwoToEyeGlow'
    monkeypatch.setattr(runtime_paths.sys,'frozen',True,raising=False)
    monkeypatch.setattr(runtime_paths.sys,'executable',str(executable))
    assert runtime_paths.project_root() == tmp_path/'code-repo'


def test_assets_paths_follow_source_and_frozen_repository(monkeypatch,tmp_path):
    monkeypatch.setattr(runtime_paths,'project_root',lambda: tmp_path/'code-repo')
    assert runtime_paths.default_dataset() == tmp_path/'assets/egobody-data'
    assert runtime_paths.default_models() == tmp_path/'assets/models_smplx_v1_1/models/smplx'
