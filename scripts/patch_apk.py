#!/usr/bin/env python3
import argparse
import json
import pathlib
import sys
import xml.etree.ElementTree as ET


def load_translations(path: pathlib.Path) -> dict[str, str]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("Die Übersetzungsdatei muss ein JSON-Objekt enthalten.")
    return {str(k): str(v) for k, v in data.items()}


def android_unescape(value: str) -> str:
    return (
        value.replace(r"\\", "\0")
        .replace(r"\n", "\n")
        .replace(r"\r", "\r")
        .replace(r"\t", "\t")
        .replace(r"\'", "'")
        .replace(r'\"', '"')
        .replace("\0", "\\")
    )


def patch_values_file(file_path: pathlib.Path, translations: dict[str, str], hits: dict[str, int]) -> bool:
    try:
        tree = ET.parse(file_path)
    except (ET.ParseError, OSError):
        return False

    root = tree.getroot()
    changed = False

    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        is_string = tag == "string"
        is_string_item = tag == "item" and element.attrib.get("type") == "string"

        if not (is_string or is_string_item):
            continue

        # Nur einfache Textressourcen ändern. Ressourcen mit eingebetteten XML-Tags
        # bleiben bewusst unangetastet, damit Formatierung und AAPT-Syntax sicher bleiben.
        if len(element) != 0 or element.text is None:
            continue

        source_value = android_unescape(element.text)
        target_value = translations.get(source_value)
        if target_value is None:
            continue

        element.text = target_value
        hits[source_value] += 1
        changed = True

    if changed:
        tree.write(file_path, encoding="utf-8", xml_declaration=True)

    return changed


def patch_tree(root: pathlib.Path, translations: dict[str, str]) -> tuple[dict[str, int], int]:
    hits = {source: 0 for source in translations}
    changed_files = 0

    res_dir = root / "res"
    if not res_dir.is_dir():
        raise FileNotFoundError(f"Ressourcenverzeichnis nicht gefunden: {res_dir}")

    # Absichtlich ausschließlich res/values* bearbeiten.
    # AndroidManifest.xml, Smali, Klassennamen, IDs und sonstiger Programmcode
    # werden niemals verändert.
    for values_dir in sorted(res_dir.glob("values*")):
        if not values_dir.is_dir():
            continue
        for file_path in sorted(values_dir.glob("*.xml")):
            if patch_values_file(file_path, translations, hits):
                changed_files += 1

    return hits, changed_files


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Übersetzt ausschließlich echte Android-String-Ressourcen in einer apktool-Ausgabe."
    )
    parser.add_argument("decoded_dir", type=pathlib.Path)
    parser.add_argument("translations", type=pathlib.Path)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Build abbrechen, wenn mindestens ein Quelltext nicht gefunden wird.",
    )
    args = parser.parse_args()

    translations = load_translations(args.translations)
    hits, changed_files = patch_tree(args.decoded_dir, translations)
    missing = [source for source, count in hits.items() if count == 0]

    print(f"Geänderte Ressourcen-Dateien: {changed_files}")
    print(f"Übersetzungen gesamt: {len(translations)}")
    print(f"Gefunden: {len(translations) - len(missing)}")
    print(f"Nicht gefunden: {len(missing)}")

    print("\nGefundene Übersetzungen:")
    for source, count in hits.items():
        if count:
            print(f"  {count:3d}x  {source}")

    if missing:
        print("\nHINWEIS: Diese Texte liegen nicht als einfache Android-String-Ressource vor:", file=sys.stderr)
        for source in missing:
            print(f"  - {source}", file=sys.stderr)
        if args.strict:
            return 2

    if changed_files == 0:
        print("FEHLER: Es wurde keine Android-String-Ressource verändert.", file=sys.stderr)
        return 3

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
