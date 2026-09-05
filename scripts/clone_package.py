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


def remove_split_requirements(text: str) -> tuple[str, int]:
    """Remove App-Bundle split requirements so the rebuilt APK is standalone-installable."""
    changes = 0

    # Attributes commonly added to the base APK of an Android App Bundle.
    for attr in ("isSplitRequired", "requiredSplitTypes", "splitTypes"):
        pattern = re.compile(rf'\s+android:{attr}="[^"]*"')
        text, count = pattern.subn("", text)
        changes += count

    # Google Play / bundletool metadata declaring that additional split APKs are required.
    split_metadata_names = (
        "com.android.vending.splits",
        "com.android.vending.splits.required",
        "com.android.vending.splits.id",
    )
    for name in split_metadata_names:
        pattern = re.compile(
            r'\s*<meta-data\b(?=[^>]*android:name="' + re.escape(name) + r'")[^>]*/>\s*',
            re.DOTALL,
        )
        text, count = pattern.subn("\n", text)
        changes += count

    return text, changes


def patch_manifest(path: pathlib.Path, old_package: str, new_package: str) -> tuple[int, int]:
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

    # The source APK is a base APK from a split/App-Bundle install. Our rebuilt APK
    # is a single standalone APK, therefore it must not require companion splits.
    text, split_changes = remove_split_requirements(text)

    if text != original:
        path.write_text(text, encoding="utf-8", newline="")
        return 1, split_changes
    return 0, split_changes


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

    manifest_changes, split_changes = patch_manifest(manifest, args.old_package, args.new_package)
    label_changes = patch_app_label(decoded_dir)

    # Fail early if the apktool rename setting was not actually written.
    yml = apktool_yml.read_text(encoding="utf-8")
    expected = re.compile(
        r"(?m)^\s*renameManifestPackage:\s*" + re.escape(args.new_package) + r"\s*$"
    )
    if not expected.search(yml):
        print("FEHLER: renameManifestPackage wurde nicht korrekt gesetzt.", file=sys.stderr)
        return 4

    # Fail early if known split requirements survived the manifest patch.
    manifest_text = manifest.read_text(encoding="utf-8")
    forbidden_split_markers = (
        'android:isSplitRequired=',
        'android:requiredSplitTypes=',
        'android:splitTypes=',
        'android:name="com.android.vending.splits.required"',
    )
    leftovers = [marker for marker in forbidden_split_markers if marker in manifest_text]
    if leftovers:
        print("FEHLER: Split-Anforderung ist noch im Manifest vorhanden:", file=sys.stderr)
        for marker in leftovers:
            print(f"  - {marker}", file=sys.stderr)
        return 5

    print(f"Neue App-ID: {args.new_package}")
    print(f"Manifest-Zusatzanpassungen: {manifest_changes}")
    print(f"Entfernte Split-Anforderungen: {split_changes}")
    print(f"App-Label-Ressourcen geändert: {label_changes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
