"""Install a per-user Linux desktop launcher for the packaged application."""
import argparse
from pathlib import Path
import shutil

DESKTOP_ID = 'ittakestwotoeyeglow'
LEGACY_DESKTOP_ID = 'eyeglow-egobody'


def quoted_exec(path):
    return '"' + str(path).replace('\\', '\\\\').replace('"', '\\"') + '"'


def install(executable, icon, applications_directory, icons_directory, template):
    executable = Path(executable).resolve()
    icon = Path(icon).resolve()
    if not executable.is_file():
        raise FileNotFoundError(f'Packaged executable not found: {executable}')
    if not icon.is_file():
        raise FileNotFoundError(f'Application icon not found: {icon}')
    applications_directory = Path(applications_directory)
    icons_directory = Path(icons_directory)
    applications_directory.mkdir(parents=True, exist_ok=True)
    icons_directory.mkdir(parents=True, exist_ok=True)
    installed_icon = icons_directory / f'{DESKTOP_ID}.png'
    shutil.copy2(icon, installed_icon)
    desktop = Path(template).read_text().replace('@EXECUTABLE@', quoted_exec(executable))
    launcher = applications_directory / f'{DESKTOP_ID}.desktop'
    launcher.write_text(desktop)
    launcher.chmod(0o755)
    (applications_directory / f'{LEGACY_DESKTOP_ID}.desktop').unlink(missing_ok=True)
    (icons_directory / f'{LEGACY_DESKTOP_ID}.png').unlink(missing_ok=True)
    return launcher, installed_icon


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description='Install the ItTakesTwoToEyeGlow Linux launcher')
    parser.add_argument('--executable', type=Path,
                        default=root / 'dist' / 'ItTakesTwoToEyeGlow' /
                        'ItTakesTwoToEyeGlow')
    parser.add_argument('--icon', type=Path,
                        default=root / 'src' / 'eyeglow_egobody' / 'resources' /
                        'icons' / 'ittakestwotoeyeglow.png')
    parser.add_argument('--applications-directory', type=Path,
                        default=Path.home() / '.local' / 'share' / 'applications')
    parser.add_argument('--icons-directory', type=Path,
                        default=Path.home() / '.local' / 'share' / 'icons' /
                        'hicolor' / '512x512' / 'apps')
    parser.add_argument('--template', type=Path,
                        default=root / 'resources' / 'linux' /
                        'ittakestwotoeyeglow.desktop.in')
    args = parser.parse_args()
    launcher, installed_icon = install(
        args.executable, args.icon, args.applications_directory,
        args.icons_directory, args.template)
    print(f'Installed launcher: {launcher}')
    print(f'Installed icon: {installed_icon}')


if __name__ == '__main__':
    main()
