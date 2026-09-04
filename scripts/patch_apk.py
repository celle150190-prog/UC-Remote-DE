#!/usr/bin/env python3
import argparse
import json
import pathlib
import re
import sys

TEXT_EXTENSIONS = {".xml", ".txt", ".json", ".html", ".js", ".kt", ".java"}
SMALI_STRING_RE = re.compile(r'(?P<prefix>\b(?:const-string(?:/jumbo)?|\.field[^=]*=)\s+[^\"]*\")(?P<value>(?:\\.|[^\"\\])*)(?P<suffix>\")')


def load_translations(path: pathlib.Path) -> dict[str, str]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("Die Übersetzungsdatei muss ein JSON-Objekt enthalten.")
    return {str(k): str(v) for k, v in data.items()}


def smali_unescape(value: str) -> str:
    return (
        value.replace(r"\\", "\0")
        .replace(r'\"', '"')
        .replace(r"\n", "\n")
        .replace(r"\r", "\r")
        .replace(r"\t", "\t")
        .replace("\0", "\\")
    )


def smali_escape(value: str) -> str:
    return (
        value.replace("\\", r"\\")
        .replace('"', r'\"')
        .replace("\n", r"\n")
        .replace("\r", r"\r")
        .replace("\t", r"\t")
    )


def patch_smali(text: str, ordered_translations, hits: dict[str, int]) -> str:
    def replace_match(match: re.Match) -> str:
        raw_value = match.group("value")
        value = smali_unescape(raw_value)
        patched_value = value

        for source, target in ordered_translations:
            count = patched_value.count(source)
            if count:
                patched_value = patched_value.replace(source, target)
                hits[source] += count

        if patched_value == value:
            return match.group(0)

        return match.group("prefix") + smali_escape(patched_value) + match.group("suffix")

    return SMALI_STRING_RE.sub(replace_match, text)


def patch_plain_text(text: str, ordered_translations, hits: dict[str, int]) -> str:
    patched = text
    for source, target in ordered_translations:
        count = patched.count(source)
        if count:
            patched = patched.replace(source, target)
            hits[source] += count
    return patched


def patch_tree(root: pathlib.Path, translations: dict[str, str]) -> tuple[dict[str, int], int]:
    hits = {source: 0 for source in translations}
    changed_files = 0
    ordered_translations = sorted(translations.items(), key=lambda item: len(item[0]), reverse=True)

    for file_path in root.rglob("*"):
        if not file_path.is_file():
            continue

        suffix = file_path.suffix.lower()
        if suffix != ".smali" and suffix not in TEXT_EXTENSIONS:
            continue

        try:
            original = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue

        if suffix == ".smali":
            patched = patch_smali(original, ordered_translations, hits)
        else:
            patched = patch_plain_text(original, ordered_translations, hits)

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
