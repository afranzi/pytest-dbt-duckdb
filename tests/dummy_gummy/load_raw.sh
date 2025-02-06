#!/bin/bash

# Variables
DATA_DIR="./data"
DB_FILE="dummy_duckdb.db"
ZIP_FILE="${DATA_DIR}/netflix-movies-and-tv-shows.zip"
MOVIES_CSV_FILE="${DATA_DIR}/netflix_titles.csv"
SCHEMA="netflix"
TABLE_MOVIES="shows"
DUCKDB_CLI=$(which duckdb)

# Dataset URL
TMDB_DATASET_URL="https://www.kaggle.com/api/v1/datasets/download/anandshaw2001/netflix-movies-and-tv-shows"

# Ensure DuckDB CLI is installed
if [ -z "$DUCKDB_CLI" ]; then
    echo "DuckDB CLI not found. Please install it before running this script."
    exit 1
fi

# Create data directory if it doesn't exist
if [ ! -d "$DATA_DIR" ]; then
    echo "Creating data directory: $DATA_DIR"
    mkdir -p "$DATA_DIR"
fi

# Download the dataset ZIP file if not already downloaded
if [ ! -f "$ZIP_FILE" ]; then
    echo "Downloading TMDb dataset..."
    curl -L -o "$ZIP_FILE" "$TMDB_DATASET_URL"
    if [ $? -ne 0 ]; then
        echo "Failed to download the dataset. Check the URL or your internet connection."
        exit 1
    fi
    echo "Dataset downloaded to $ZIP_FILE."
else
    echo "Dataset ZIP file already exists at $ZIP_FILE. Skipping download."
fi

# Extract the ZIP file
echo "Extracting dataset..."
unzip -o "$ZIP_FILE" -d "$DATA_DIR"
if [ $? -ne 0 ]; then
    echo "Failed to extract the ZIP file. Ensure 'unzip' is installed."
    exit 1
fi
echo "Dataset extracted to $DATA_DIR."

# Ensure the required CSV files exist
if [ ! -f "$MOVIES_CSV_FILE" ]; then
    echo "Required CSV files not found in the extracted dataset."
    exit 1
fi

# Create and populate the DuckDB database
echo "Creating DuckDB database and tables..."
$DUCKDB_CLI "$DB_FILE" <<EOF
CREATE SCHEMA IF NOT EXISTS  $SCHEMA;
CREATE OR REPLACE TABLE $SCHEMA.$TABLE_MOVIES AS SELECT * FROM read_csv_auto('$MOVIES_CSV_FILE', header=True);
EOF

if [ $? -eq 0 ]; then
    echo "DuckDB database created at $DB_FILE, and tables '$TABLE_MOVIES' populated successfully."
else
    echo "Failed to create DuckDB database or populate the tables."
    exit 1
fi

echo "Setup complete. You can now use the DuckDB database at $DB_FILE."
