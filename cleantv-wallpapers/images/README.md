# CleanTV wallpapers: drop your images here

Put photos directly into this folder and push to `main`. The GitHub Action
`.github/workflows/cleantv-wallpapers.yml` then generates everything the TV needs
in `../generated/` and `../index.json` and commits them. You never edit those files
by hand.

## Warning: the originals are public

**Every file in this folder is public in this repository, including its EXIF data:
the GPS position where a photo was taken, the camera, and the date and time.**
Deleting a file later does not remove it from the Git history. Remove the location
data before you add a photo (for example by exporting a copy without location data).
The Action prints a warning for every original that still carries a GPS position.
The generated files on the TV are re-encoded and carry no metadata.

## Rules

- Formats: JPG (`.jpg`, `.jpeg`), PNG (`.png`) or WebP (`.webp`). Other files fail
  the run with a clear error, as do files that cannot be decoded and files over 30 MB.
  16-bit PNGs (also black-and-white ones) are reduced to 8 bit.
- Landscape photos work best. The generator applies the EXIF orientation, crops the
  centre to 16:9 and scales it to 1920 x 1080. Portrait or smaller photos are cropped
  or enlarged, with a warning.
- Transparent areas become black.
- At most 200 images; the index must also stay under 256 KiB, which with typical
  names allows about 180.
- Files directly in this folder only; subfolders are not read. This README and files
  starting with a dot are ignored.

## Titles and IDs

The title shown on the TV comes from the file name: the extension is dropped, `_` and
`-` become spaces and repeated spaces collapse to one. `Sonnenuntergang_am-See.jpg`
is shown as "Sonnenuntergang am See". Titles may have at most 120 characters.

The ID is `aw-` plus the title in lower case, with ä, ö, ü and ß written as ae, oe,
ue and ss, other accents removed and everything else turned into hyphens, at most 40
characters: `aw-sonnenuntergang-am-see`. Images whose IDs would be equal get `-2`,
`-3` and so on, in file-name order. The TV remembers the chosen wallpaper and the
favourites by ID, so renaming a file makes it a new wallpaper there; replacing a file
under the same name keeps the ID and updates the image.

Removing an image removes its generated files and its entry. A TV that shows it keeps
it until another wallpaper is chosen.
