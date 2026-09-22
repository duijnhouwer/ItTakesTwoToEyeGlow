from pathlib import Path

from scripts.install_linux_launcher import install


def test_linux_launcher_uses_packaged_executable_icon_and_singleton_flag(tmp_path):
    executable = tmp_path / 'app dir' / 'ItTakesTwoToEyeGlow'
    executable.parent.mkdir()
    executable.write_bytes(b'executable')
    icon = tmp_path / 'icon.png'
    icon.write_bytes(b'png')
    template = (Path(__file__).resolve().parents[2] / 'resources' / 'linux' /
                'ittakestwotoeyeglow.desktop.in')
    applications = tmp_path / 'applications'
    icons = tmp_path / 'icons'
    applications.mkdir()
    icons.mkdir()
    legacy_launcher = applications / 'eyeglow-egobody.desktop'
    legacy_icon = icons / 'eyeglow-egobody.png'
    legacy_launcher.write_text('Name=EyeGlow EgoBody')
    legacy_icon.write_bytes(b'old')
    launcher, installed_icon = install(
        executable, icon, applications, icons, template)
    text = launcher.read_text()
    assert f'Exec="{executable.resolve()}" --single-instance' in text
    assert 'Icon=ittakestwotoeyeglow' in text
    assert launcher.name == 'ittakestwotoeyeglow.desktop'
    assert installed_icon.name == 'ittakestwotoeyeglow.png'
    assert installed_icon.read_bytes() == b'png'
    assert launcher.stat().st_mode & 0o111
    assert not legacy_launcher.exists()
    assert not legacy_icon.exists()
