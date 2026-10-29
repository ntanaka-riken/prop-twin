#!/bin/sh
# Download the large files (videos, 3D scans, scratch folders, raw session logs) attached to the GitHub
# release into media/release/ and check them against media/SHA256SUMS.
# Needs the GitHub CLI (gh) logged in with access to this repository.
#   sh media/fetch_media.sh                 # everything (about 1.1 GB)
#   sh media/fetch_media.sh 'IMG_578*'      # only some files
set -e
cd "$(dirname "$0")"
mkdir -p release
gh release download media-2026-10-29 --repo ntanaka-riken/prop-twin --dir release --skip-existing --pattern "${1:-*}"
cd release && shasum -a 256 -c --ignore-missing ../SHA256SUMS
