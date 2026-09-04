#!/usr/bin/env python3
import argparse
import json
import pathlib
import sys

TEXT_EXTENSIONS = {".smali", ".xml", ".txt", ".json", ".html", ".js", ".kt", ".java"}


def load_translations(path: pathlib.Path) -> dict[str, str]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("Die Übersetzungsdatei muss ein JSON-Objekt enthalten.")
    return {str(k): str(v) for k, v in data.items()}


def patch_tree(root: pathlib.Path, translations: dict[str, str]) -> tuple[dict[str, int], int]:
    hits = {source: 0 for source in translations}
    changed_files = 0
    ordered_translations = sorted(translations.items(), key=lambda item: len(item[0]), reverse=True)

    for file_path in root.rglob("*"):
        if not file_path.is_file() or file_path.suffix.lower() not in TEXT_EXTENSIONS:
            continue

        try:
            original = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue

        patched = original
        for source, target in ordered_translations:
            count = patched.count(source)
            if count:
                patched = patched.replace(source, target)
                hits[source] += count

        if patched != original:
            file_path.write_text(patched, encoding="utf-8", newline="")
            changed_files += 1

    return hits, changed_files


def main() -> int:
    parser = argparse.ArgumentParser(description="Patcht UC-Remote-Texte in einem apktool-Ausgabeverzeichnis.")
    parser.add_argument("decoded_dir", type=pathlib.Path)
    parser.add_argument("translations", type=pathlib.Path)
    parser.add_argument("--strict", action="store_true", help="Build abbrechen, wenn mindestens ein Quelltext nicht gefunden wird.")
    args = parser.parse_args()

    translations = load_translations(args.translations)
    hits, changed_files = patch_tree(args.decoded_dir, translations)
    missing = [source for source, count in hits.items() if count == 0]

    print(f"Geänderte Dateien: {changed_files}")
    print(f"Übersetzungen gesamt: {len(translations)}")
    print(f"Gefunden: {len(translations) - len(missing)}")
    print(f"Nicht gefunden: {len(missing)}")

    print("\nGefundene Übersetzungen:")
    for source, count in hits.items():
        if count:
            print(f"  {count:3d}x  {source}")

    if missing:
        print("\nWARNUNG: Folgende Texte wurden nicht gefunden:", file=sys.stderr)
        for source in missing:
            print(f"  - {source}", file=sys.stderr)
        if args.strict:
            return 2

    if changed_files == 0:
        print("FEHLER: Es wurde keine Datei verändert.", file=sys.stderr)
        return 3

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
