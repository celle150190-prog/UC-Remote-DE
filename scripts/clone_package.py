#!/usr/bin/env python3
import argparse
import pathlib
import re
import sys


def patch_apktool_yml(path: pathlib.Path, new_package: str) -> None:
    text = path.read_text(encoding="utf-8")

    # apktool stores renameManifestPackage indented below packageInfo.
    # Preserve the existing indentation and replace the value in place.
    pattern = re.compile(r"(?m)^(?P<indent>\s*)renameManifestPackage:\s*.*$")
    match = pattern.search(text)
    if match:
        indent = match.group("indent")
        text = pattern.sub(
            lambda m: f"{indent}renameManifestPackage: {new_package}",
            text,
            count=1,
        )
    else:
        # Fallback: insert it directly below packageInfo with normal YAML indentation.
        package_info = re.compile(r"(?m)^(?P<indent>\s*)packageInfo:\s*$")
        match = package_info.search(text)
        if not match:
            raise RuntimeError("packageInfo in apktool.yml nicht gefunden")
        child_indent = match.group("indent") + "  "
        insert_at = match.end()
        text = text[:insert_at] + f"\n{child_indent}renameManifestPackage: {new_package}" + text[insert_at:]

    path.write_text(text, encoding="utf-8", newline="")


def patch_manifest(path: pathlib.Path, old_package: str, new_package: str) -> int:
    text = path.read_text(encoding="utf-8")
    original = text

    # Provider authorities must be unique for side-by-side installation.
    text = re.sub(
        r'(android:authorities=")' + re.escape(old_package) + r'([^\"]*)(")',
        lambda m: m.group(1) + new_package + m.group(2) + m.group(3),
        text,
    )

    # Custom permissions owned by this application should also be unique.
    def patch_permission_tag(match: re.Match) -> str:
        tag = match.group(0)
        return tag.replace(
            f'android:name="{old_package}.',
            f'android:name="{new_package}.',
        )

    text = re.sub(r'<(?:permission|uses-permission)\b[^>]*>', patch_permission_tag, text)

    if text != original:
        path.write_text(text, encoding="utf-8", newline="")
        return 1
    return 0


def patch_app_label(decoded_dir: pathlib.Path) -> int:
    changed = 0
    for values_dir in decoded_dir.glob("res/values*"):
        if not values_dir.is_dir():
            continue
        for xml_file in values_dir.glob("*.xml"):
            try:
                text = xml_file.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            original = text
            text = re.sub(
                r'(<string\b[^>]*name="app_name"[^>]*>)UC Remote(</string>)',
                r'\1UC Remote DE\2',
                text,
            )
            if text != original:
                xml_file.write_text(text, encoding="utf-8", newline="")
                changed += 1
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description="Bereitet UC Remote für parallele Installation als eigene App-ID vor.")
    parser.add_argument("decoded_dir", type=pathlib.Path)
    parser.add_argument("--old-package", default="com.ucremote.android")
    parser.add_argument("--new-package", default="com.ucremote.android.de")
    args = parser.parse_args()

    decoded_dir = args.decoded_dir
    apktool_yml = decoded_dir / "apktool.yml"
    manifest = decoded_dir / "AndroidManifest.xml"

    if not apktool_yml.is_file() or not manifest.is_file():
        print("FEHLER: apktool.yml oder AndroidManifest.xml fehlt.", file=sys.stderr)
        return 2

    try:
        patch_apktool_yml(apktool_yml, args.new_package)
    except RuntimeError as exc:
        print(f"FEHLER: {exc}", file=sys.stderr)
        return 3

    manifest_changes = patch_manifest(manifest, args.old_package, args.new_package)
    label_changes = patch_app_label(decoded_dir)

    # Fail early if the apktool rename setting was not actually written.
    yml = apktool_yml.read_text(encoding="utf-8")
    expected = re.compile(
        r"(?m)^\s*renameManifestPackage:\s*" + re.escape(args.new_package) + r"\s*$"
    )
    if not expected.search(yml):
        print("FEHLER: renameManifestPackage wurde nicht korrekt gesetzt.", file=sys.stderr)
        return 4

    print(f"Neue App-ID: {args.new_package}")
    print(f"Manifest-Zusatzanpassungen: {manifest_changes}")
    print(f"App-Label-Ressourcen geändert: {label_changes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
