# UC Remote DE

Automatischer Patch- und Build-Prozess für eine deutsch übersetzte Variante der Android-App **UC Remote**.

## Ziel

Die originale UC-Remote-APK wird nicht dauerhaft im Repository gespeichert. Stattdessen wird bei einem Build eine bereitgestellte Original-APK dekompiliert, bekannte englische UI-Texte werden anhand einer zentralen Übersetzungsliste ersetzt, anschließend wird die APK neu gebaut und signiert.

## Struktur

- `translations/de.json` – zentrale Englisch→Deutsch-Übersetzungen
- `scripts/patch_apk.py` – ersetzt bekannte Texte in dekompilierten Smali-/Resource-Dateien
- `.github/workflows/build.yml` – automatischer Build über GitHub Actions

## Signatur

Die gepatchte APK kann nicht mit der Originalsignatur von Unfolded Circle signiert werden. Für dauerhaft updatefähige UC-Remote-DE-Builds sollte deshalb immer derselbe eigene Keystore verwendet werden. Dieser gehört **nicht** ins Repository, sondern als GitHub Actions Secret hinterlegt.

## Hinweis

Da UC Remote große Teile der Oberfläche mit Jetpack Compose umsetzt, liegen sichtbare Texte teilweise direkt im kompilierten DEX/Smali-Code. Bei App-Updates können deshalb neue oder geänderte Texte hinzukommen. Der Build meldet, welche Übersetzungen gefunden und welche nicht gefunden wurden.
