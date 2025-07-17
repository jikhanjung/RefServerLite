# RefServerLite Scripts

This directory contains utility scripts for RefServerLite.

## Zotero Import Script

The `import_from_zotero.py` script allows you to import PDF documents and metadata from your Zotero library into RefServerLite.

### Setup

1. **Install dependencies**: Make sure you have installed all requirements:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure the script**: Copy the example configuration and update with your credentials:
   ```bash
   cp config.yml.example config.yml
   # Edit config.yml with your Zotero and RefServerLite credentials
   ```

3. **Get your Zotero credentials**:
   - Library ID: Found in Zotero Settings > Feeds/API
   - API Key: Create at https://www.zotero.org/settings/keys (needs "Library - Read" permission)

### Usage

#### First Run (Interactive Setup)
If you don't have a configuration file, the script will help you create one:
```bash
python import_from_zotero.py
# The script will prompt for Zotero and RefServerLite credentials
```

#### Basic Import
Import all items from your Zotero library:
```bash
python import_from_zotero.py
# Interactive mode: asks for confirmation at each step
```

#### Non-Interactive Mode
For automated scripts or CI/CD:
```bash
python import_from_zotero.py --non-interactive
# Uses defaults, no user prompts
```

#### Dry Run
See what would be imported without actually importing:
```bash
python import_from_zotero.py --dry-run
```

#### Import from Specific Collection
```bash
# Using collection ID (8-character key)
python import_from_zotero.py --collection ABCD1234

# Using collection name (case-insensitive)
python import_from_zotero.py --collection "Research Papers"
python import_from_zotero.py --collection "antarctica papers"
```

#### Import Recent Changes Only
Import items modified since a specific Zotero library version:
```bash
python import_from_zotero.py --since-version 12345
```

#### Limit Number of Items
Import only the first N items (useful for testing):
```bash
python import_from_zotero.py --limit 10
```

#### Cache Management
The script automatically caches downloaded PDFs and metadata for efficiency and reliability:

```bash
# Show cache statistics
python import_from_zotero.py --cache-stats

# Clean up old cache files (older than 30 days)
python import_from_zotero.py --cache-cleanup 30

# Invalidate cache for specific item
python import_from_zotero.py --cache-invalidate ABCD1234

# Disable cache (force fresh downloads)
python import_from_zotero.py --no-cache --collection "Research"
```

### Features

- **Smart Caching**: PDFs and metadata are cached in `scripts/zotero_cache/` for retry and efficiency
- **Progress Tracking**: The script saves progress to `zotero_import_progress.json` and can resume interrupted imports
- **Duplicate Detection**: Automatically skips items that already exist in RefServerLite
- **Batch Processing**: Processes items in configurable batches with delays to respect API rate limits
- **Detailed Reporting**: Generates a JSON report with import results
- **Error Handling**: Individual item failures don't stop the entire import
- **Cache Management**: Automatic PDF caching with integrity checking and cleanup options

### Output

The script will:
1. Display progress in the console
2. Save progress to `zotero_import_progress.json` for resume capability
3. Generate a detailed report in `import_report_YYYYMMDD_HHMMSS.json`

### Troubleshooting

1. **Authentication Failed**: Check your RefServerLite credentials in `config.yml`
2. **Zotero API Errors**: Verify your Zotero library ID and API key
3. **Rate Limiting**: Increase `delay_seconds` in the configuration
4. **PDF Download Failures**: Ensure your Zotero storage is synced