# Reconstructing Ledger

The complete guide includes a pinned 75-file base application and a seven-file
mobile overlay. The overlay replaces two existing files and adds five, producing
80 application files in a fresh destination.

Run from this directory:

```sh
python3 RESTORE-LEDGER-SOURCE.py \
  'LEDGER — COMPLETE BUILD AND LIGHT MODE RECONSTRUCTION.md' \
  Ledger-With-Mobile --with-mobile
```

Every embedded byte count and SHA256 is checked before writing. The destination
must not already exist. Omit `--with-mobile` only to reconstruct the earlier base
snapshot. Use a separate synthetic-data directory for testing.

The guide records companion ZIP packages from the original shareable bundle;
those archives are not required by the extractor and are not distributed in this
repository. The repository's current source may acquire later changes beyond the
embedded snapshot. Treat the guide as a versioned reconstruction reference.

Private deployment addresses, personalized launchers, credentials, financial
records and personal screenshots are not included.
