# CleanTV Add-ons

**Erweiterungen für [CleanTV](https://github.com/AntoinS/CleanTV): herunterladen, einrichten und unabhängig aktualisieren.**

Dieses Repository enthält den öffentlichen Paketkatalog, freigegebene Pakete, den Quellcode der nativen iPhone-Erweiterung und Beispiele für eigene Add-ons. Die Adresse `cleanframe-addons` bleibt erhalten, damit bestehende TVs weiterhin ihre Downloads erreichen.

## Verfügbare Erweiterungen

| Add-on | Möglichkeiten | Voraussetzungen und Grenzen |
| --- | --- | --- |
| Spotify | Cover, Titel, Interpret, Fortschritt und Steuerung; kompakte/aufgeklappte Darstellung, Transparenz und Coverfarbe; QR-Anmeldung und Abmelden in CleanTV | Spotify-TV-App und eigenes Konto; geräteübergreifende Steuerung über eine eingerichtete Spotify Web API. Das JSON-Paket aktiviert den im Host enthaltenen Spotify-Adapter. |
| iPhone Remote | Apple-TV-Fernbedienung im iPhone-Kontrollzentrum: Navigation, Home, Zurück, Medien, Lautstärke und unterstützte Texteingabe | Eigenständige Android-App, derzeit experimentell und am Philips geprüft. Erscheint unter dem Gerätenamen des TVs. Kein laufender Mac nötig. Kein Siri oder AirPlay-Streaming. |

[Remote-Einrichtung, Architektur und Testgrenzen](addons/apple-remote/README.md) · [Releases](https://github.com/AntoinS/cleanframe-addons/releases) · [Native Add-on-API](API-2.md)

## Am Fernseher verwalten

Öffne **CleanTV → Einstellungen → Add-ons**. Unter **Installiert** findest du vorhandene Erweiterungen; unter **Entdecken** die freigegebenen Pakete. Details zeigen Version, Anbieter, Freigaben und passende Aktionen.

- **Herunterladen:** Paket prüfen und installieren; Android bestätigt native APKs.
- **Einrichten:** sichtbare Spotify- und iPhone-Einstellungen direkt in CleanTV öffnen. Android verwaltet erforderliche Systemfreigaben.
- **Aktivieren/Deaktivieren:** die Erweiterung ein- oder ausschalten, ohne sie zu entfernen.
- **Aktualisieren:** vorhandene Einstellungen, Aktivierung und Kopplungen erhalten.
- **Deinstallieren:** Erweiterung entfernen. Android löscht dabei die Daten und Kopplungen einer nativen App. Beim Spotify-Widget bleiben Host-Konto und Gestaltung erhalten, bis du ausdrücklich abmeldest.

Ab CleanTV 0.8.3 zeigen blaue Punkte neue Updates an. **Alle aktualisieren** verarbeitet sie nacheinander; jedes APK benötigt weiterhin Androids Bestätigung. Abbruch oder Fehler stoppt die restlichen Updates. Ein neuer Katalogeintrag deaktiviert keine installierte Version und verhindert deren Deinstallation nicht. Ein älterer Katalog bietet kein Downgrade an.

Die Installation wird anhand des tatsächlichen Android-Pakets und der vertrauenswürdigen Signatur geprüft. Downloads verlangen zusätzlich die angekündigte Version und Prüfsumme. Offline bleiben vorhandene Pakete nutzbar.

## iPhone Remote einrichten

Aktiviere das Add-on in seinen CleanTV-Einstellungen. Auf dem unterstützten Philips kann die einmalige Freigabe **CleanTV · Automatische TV-Einrichtung** den Philips-Kopplungscode während der eigenen Einrichtung bestätigen. Der Zugriff ist auf dieses zeitlich begrenzte Kopplungsfenster beschränkt.

Wähle anschließend den Gerätenamen deines TVs in der Apple-TV-Fernbedienung auf dem iPhone und bestätige die Kopplung mit dem angezeigten Code. Für Texteingabe kannst du die **CleanTV iPhone Keyboard** in Android freigeben und auswählen. Geräte lassen sich einzeln entkoppeln.

Am Referenzgerät wurden Kopplung, Wiederverbindung, Navigation, Lautstärke, Play/Pause und Live-Texteingabe in Spotify geprüft. Weitere Apps, die vollständige Standby-/Neustartmatrix und Tiefschlaf-Aufwecken sind nicht zugesichert. App-eigene Tastaturen können die Texteingabeschnittstelle umgehen.

## Eigene Add-ons entwickeln

**API 1:** deklarative JSON-Pakete für Text, Uhr und den reservierten Spotify-Anbieter. Sie enthalten keinen ausführbaren JavaScript- oder HTML-Code. Beginne mit [examples](examples/) und [package.schema.json](package.schema.json). Bis zu drei zusätzliche Home-Widgets sind möglich.

**API 2:** ergänzt separat installierte, signierte Android-Apps. Der Host lädt keinen fremden Code in seine WebView. Identität, Signatur und Dienstschnittstelle werden geprüft. Neue native Paketkennungen benötigen eine ausdrückliche Host-Integration und Prüfung; ein Katalogeintrag allein reicht nicht. Siehe [API-2.md](API-2.md) und [native-package.schema.json](native-package.schema.json).

1. Vergib eine stabile Paketkennung und semantische Version.
2. Verwende die Beispiele und dokumentiere Funktionen, Freigaben und Grenzen.
3. Prüfe Deutsch/Englisch, Fernbedienungsfokus sowie 720p, 1080p und 4K.
4. Reiche einen Pull Request mit Quellcode, Lizenzangaben, Prüfergebnissen und Screenshots ein. Erst freigegebene Pakete gelangen in den Katalog.

Der Mac-Editor von CleanTV bietet eine getrennte Add-on-Simulation und lesende TV-Diagnose. Simulation ersetzt keine Geräteprüfung und wird nicht als TV-Konfiguration übertragen.

## Kataloge, Releases und Herkunft

`catalog.json` erhält die API-1-Kompatibilität; `catalog-v2.json` ergänzt native Pakete. TVs lesen den freigegebenen Katalog von `main`. Paketversionen, Downloadpfade und Release-Tags bleiben unveränderlich. Add-ons und Katalog haben unabhängige Versionsnummern; Android-Versioncodes steigen monoton.

Die nativen Quellen, festgelegten Abhängigkeiten und ein lokaler Builder sind enthalten. Signierschlüssel, Kontodaten und private Gerätekonfiguration bleiben lokal. Lizenz- und Herkunftshinweise stehen in [LICENSE](LICENSE), den einzelnen Paketen und den [Remote-Hinweisen](addons/apple-remote/NOTICE.md). CleanTV basiert auf [CleanFrame von nthnclrk](https://github.com/nthnclrk/CleanFrame).

## CleanTV catalog (Samsung)

The CleanTV Samsung host reads only `cleantv-catalog.json`; `catalog.json` and `catalog-v2.json` remain unchanged for upstream hosts and clean upstream syncs. The schema is [cleantv-catalog.schema.json](cleantv-catalog.schema.json).

Each entry is a declarative API 1 package with the metadata rules of `package.schema.json` (name, description, author, license, version `x.y.z`), plus `path` and the lowercase SHA-256 of that file's exact bytes. The package file equals the entry without `path` and `sha256`, with the same JSON types (`1`, `1.0` and `true` differ). Packages contain no executable code; behaviour lives in the host. Limits: 32 entries, unique IDs, 64 KiB per package, 128 KiB for the catalog.

| Kind | Package path | Rules |
| --- | --- | --- |
| `text`, `clock` | `packages/<id>/<version>.json` | As in `package.schema.json` (optional `text`, `timeZone` up to 64 characters). |
| `spotify` | `packages/<id>/<version>.json` | The ID must be `spotify`. The catalog lists the upstream `packages/spotify/1.0.0.json` unchanged; the Samsung host adds the Spotify Web API adapter and the QR sign-in relay itself. |
| `wallpapers` | `cleantv-packages/<id>/<version>.json` | CleanTV only. Requires `index`, the repository path `cleantv-wallpapers/index.json`. |
| `weather` | `cleantv-packages/<id>/<version>.json` | CleanTV only. The ID must be `cleantv-weather` (the host refuses any other); no additional fields. Listed as `Wetter` 1.0.0. |

`cleantv-packages/` keeps the CleanTV-only kinds out of the upstream `packages/` check, which knows only `package.schema.json`. Every file there must be a `weather` or `wallpapers` package at its own `<id>/<version>` path.

The TV measures text in UTF-16 code units, as JavaScript does, so an emoji or another character outside the Basic Multilingual Plane counts twice: name, description, author and license allow 240 units, `text` 500 units. The catalog and every package must be UTF-8 without a byte order mark; Windows PowerShell 5.1 `Out-File` writes UTF-16 by default. One over-long entry or a catalog in another encoding fails the whole catalog refresh on every TV, so `validate.py` rejects both.

`python scripts/validate.py` checks this catalog as well, and `python scripts/test_cleantv_catalog.py` tests those checks. Hash the committed bytes: a Windows checkout with `core.autocrlf` may change line endings, so `git show HEAD:<path> | sha256sum` is the reliable value.

### CleanTV wallpapers

The `cleantv-wallpapers` package (kind `wallpapers`) points the TV at `cleantv-wallpapers/index.json`. The owner drops photos into [cleantv-wallpapers/images/](cleantv-wallpapers/images/README.md) (read its warning: the originals and their EXIF data, including GPS positions, are public). On every push to `main` that touches `cleantv-wallpapers/images/` or `cleantv-wallpapers/tools/`, and on a manual run, `.github/workflows/cleantv-wallpapers.yml` runs `cleantv-wallpapers/tools/generate.py` (Pillow and NumPy, pinned in `tools/requirements.txt`), validates the result and, with `cleantv-wallpapers/tools/publish.sh`, commits only `cleantv-wallpapers/generated/` and `index.json` as `github-actions[bot]` with `[skip ci]`. Nothing is committed when the output did not change. When `main` moved during the run (for example through a merged catalog change, which starts no new run), the bot commit is rebased onto the new tip and pushed again, up to three times; if the generated files themselves changed meanwhile, the rebase conflicts and the run fails with an error, so run the workflow again.

Each image becomes `generated/<id>/` with seven baseline JPEGs: `image.jpg` (1920 x 1080), `thumb.jpg` (512 x 288), `panel.jpg` (320 x 180) and the materials `study-soft.jpg`, `field-blur.jpg`, `field-frost.jpg` and `field-clear.jpg`, made with the recipe of CleanTV's `scripts/build-materials.mjs` (see the header of `generate.py`). `index.json` has the form `{"api":1,"entries":[{"id","title","rev","tone","ut":{"tr","br"},"frostVeil","listColumn"?,"dockQuiet"?,"clockMist"?,"files":{"<role>":{"path","size","sha256"}}}]}`; the roles are `jpg`, `thumb`, `panel`, `study-soft`, `field-blur`, `field-frost` and `field-clear`, `rev` is the first 12 hex digits of the `jpg` checksum, and the schema is [cleantv-wallpapers/index.schema.json](cleantv-wallpapers/index.schema.json). The same images give the same bytes.

`scripts/validate.py` checks the index whenever it exists or a `wallpapers` package is listed: at most 200 entries and 262144 bytes, unique IDs, titles of at most 120 UTF-16 code units, exact paths `cleantv-wallpapers/generated/<id>/<file>`, per-file limits (4 MiB photo, 2 MiB per material, 256 KiB thumbnail, 64 KiB panel), the size and SHA-256 of every file, and no file in `generated/` without an entry. `python cleantv-wallpapers/tools/test_generate.py` synthesises originals at runtime and runs the generator twice; `python cleantv-wallpapers/tools/test_publish.py` runs `publish.sh` against temporary Git repositories (it needs `git` and `bash`); `check.yml` runs both, the first with the pinned requirements.
