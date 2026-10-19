# CoolMS sounds

The sounds CoolMS plays when something arrives, from one source, so the admin, the desktop workspace and the mobile
apps sound the same.

There is one sound per kind of arrival. A kind's id is the same string everywhere: in the platform's notification
registry, in a client's settings and mutes, and in an Android app's notification channel.

| Kind | When | Sound |
|---|---|---|
| `ring` | a call for you | two soft chords, twice, then a rest; it loops while the call rings |
| `message` | a direct message, or a mention | a short rising two-note pop |
| `visitor` | a website visitor waiting | three ascending notes |
| `task` | a task assigned to you | one warm ding |
| `mail` | mail arriving | a soft falling two-note figure, the quietest |
| `bell` | a notification | a struck bell |

## What is here

| Path | What it is |
|---|---|
| `sources/<kind>.wav` | The master of each sound: mono, 48 kHz, 16-bit PCM. |
| `sounds.json` | One entry per kind: its versions, its source and the source's sha256, its length, whether it loops, and its origin, licence and author. |
| `dist/web/<kind>.ogg`, `dist/web/<kind>.m4a` | For browsers: Opus, and AAC for browsers that do not play Opus. |
| `dist/android/raw/<kind>.ogg` | For an Android app's `res/raw`: Vorbis. |
| `dist/ios/<kind>.caf` | For an iOS app's bundle: IMA4 (IMA ADPCM), which iOS plays as a notification sound, at about a quarter of linear PCM's size. Each file is under 30 seconds, as iOS requires. iOS cannot loop a notification sound, so the ring is its loop repeated to 20 seconds. |
| `dist/build.json` | What was built: each file's sha256, codec and length, the source it was built from, and the encoder. |
| `tools/synth.py` | Makes the sources, each from a recipe in the file. Python standard library only. |
| `tools/encode.py` | Encodes the sources into `dist/` with the encoder image. |
| `tools/encoder/Dockerfile` | The encoder: ffmpeg from Debian's packages, on a Debian base pinned by digest. A build-time tool only. |
| `tools/check.py` | The checks, below. |

Never edit a file in `dist/` by hand. Change the source, then encode again.

## Origin and licence

Every sound here is original: made for CoolMS by `tools/synth.py`, with no recorded or sampled material. The sounds
and the code are under the MIT licence (`LICENSE`). `sounds.json` records the origin, licence and author of each
sound. A sound that comes from elsewhere must be licensed for redistribution, and is recorded with `origin:
licensed`, its licence, and where it came from.

## Versions: `sound` and `build`

Each kind has two numbers in `sounds.json`:

- **`sound`** goes up when the sound itself changes, which means a new source. An Android app names its notification
  channel after the kind and this number. A channel's sound cannot change once it exists, so a new `sound` means a
  new channel, and the person's settings for the old channel do not carry over. A new `sound` is therefore a real
  change of sound, never a re-encode.
- **`build`** goes up when the same sound is encoded again, put into another format, or trimmed. It never means a
  new channel.

`tools/check.py` holds these rules against the version being merged into:
- a new source without a new `sound` is refused;
- a new `sound` without a new source is refused;
- a re-encoded file without a new `build` is refused.

## Making, encoding and checking

```sh
python3 tools/synth.py              # writes sources/ from the recipes
python3 tools/synth.py --check      # writes nothing; says whether each source is what its recipe writes
python3 tools/encode.py             # encodes sources/ into dist/ (needs Docker; builds the encoder image once)
python3 tools/check.py              # checks the manifest, the sources and dist/ against origin/develop
```

`tools/check.py` answers CLEAR (exit 0), FOUND (exit 1), or UNEVALUABLE (exit 2) when a rule could not be looked at,
for example when the version to compare with could not be read. `--against <ref>` names another version to compare
with, and `--against none` says there is none (the first version).

## Using the sounds

Take the files at a tag. This package publishes to no registry.

- **Web:** `dist/web/<kind>.ogg`, with `dist/web/<kind>.m4a` as the fallback.
- **Android:** copy `dist/android/raw/` into the app's `res/raw/`. Name each notification channel after the kind and
  its `sound` number.
- **iOS:** add `dist/ios/<kind>.caf` to the app bundle.
