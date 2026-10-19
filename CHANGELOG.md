# Changelog

All notable changes to the CoolMS sounds are listed here. Versions follow [semantic versioning](https://semver.org/).
Each sound's own `sound` and `build` numbers are in `sounds.json`.

## Unreleased

The first version: six original sounds, one per kind, each at sound 1, build 1.

- `ring`, `message`, `visitor`, `task`, `mail` and `bell`, made by `tools/synth.py`.
- Encoded for browsers (Opus, AAC), Android (Vorbis) and iOS (linear PCM in CAF, each under 30 seconds).
- `tools/check.py` checks the manifest, the sources, the built files and the `sound` and `build` rules.
