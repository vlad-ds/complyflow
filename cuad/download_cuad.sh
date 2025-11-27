#!/bin/bash
# Download CUAD (Contract Understanding Atticus Dataset) v1
# Source: https://zenodo.org/records/4595826
# License: CC BY 4.0

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

ZIP_FILE="CUAD_v1.zip"
DOWNLOAD_URL="https://zenodo.org/records/4595826/files/CUAD_v1.zip?download=1"
EXPECTED_MD5="c38f490a984420b8a62600db401fafd5"

echo "CUAD Dataset Downloader"
echo "======================="
echo ""

# Check if already downloaded
if [ -f "$ZIP_FILE" ]; then
    echo "File $ZIP_FILE already exists."
    read -p "Re-download? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Skipping download."
    else
        rm "$ZIP_FILE"
    fi
fi

# Download if needed
if [ ! -f "$ZIP_FILE" ]; then
    echo "Downloading CUAD_v1.zip (105.9 MB)..."
    curl -L -o "$ZIP_FILE" "$DOWNLOAD_URL"
    echo "Download complete."
fi

# Verify checksum
echo "Verifying checksum..."
if command -v md5sum &> /dev/null; then
    ACTUAL_MD5=$(md5sum "$ZIP_FILE" | cut -d' ' -f1)
elif command -v md5 &> /dev/null; then
    ACTUAL_MD5=$(md5 -q "$ZIP_FILE")
else
    echo "Warning: md5 command not found, skipping verification"
    ACTUAL_MD5="$EXPECTED_MD5"
fi

if [ "$ACTUAL_MD5" != "$EXPECTED_MD5" ]; then
    echo "ERROR: Checksum mismatch!"
    echo "Expected: $EXPECTED_MD5"
    echo "Actual:   $ACTUAL_MD5"
    exit 1
fi
echo "Checksum OK."

# Extract if needed
if [ ! -d "CUAD_v1" ]; then
    echo "Extracting..."
    unzip -q "$ZIP_FILE"
    echo "Extracted to CUAD_v1/"
else
    echo "CUAD_v1/ already exists, skipping extraction."
fi

echo ""
echo "Done! CUAD dataset is ready."
echo "Run 'python extract_metadata.py' to extract contracts."
