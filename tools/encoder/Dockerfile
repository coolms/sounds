# The sound package's encoder: ffmpeg from Debian's own packages, on a Debian base pinned by digest. A build-time
# tool only: tools/encode.py runs it with no network, as the calling user, on sources/ into dist/.
#
# The ffmpeg version is pinned too. When Debian's archive moves past it, the build fails rather than quietly encoding
# with another version: raise FFMPEG_VERSION deliberately, re-encode, and bump each kind's `build` in sounds.json.
FROM debian:bookworm-slim@sha256:7c7b2c966bc9ee8cedfeef67e0e279108992c77681fa595db4a9d65c06ccc587

ARG FFMPEG_VERSION=7:5.1.9-0+deb12u1

RUN apt-get update \
 && apt-get install -y --no-install-recommends "ffmpeg=${FFMPEG_VERSION}" \
 && rm -rf /var/lib/apt/lists/*

USER 65534:65534
WORKDIR /work
ENTRYPOINT ["ffmpeg"]
