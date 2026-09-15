# WikiData Batch Uploader

A Windows desktop client for bulk-uploading datasets to Wikidata, with an interface modeled after Wikidata itself.

## Features

- Scan local folders for data sheets (`.xlsx`, `.csv`) and images (`.jpg`, `.jpeg`, `.png`, `.tif`, `.tiff`).
- Load tabular data into a preview grid for review.
- Extract image metadata locally: EXIF, GPS, camera make/model, IPTC, XMP, PNG text chunks.
- Schema mapping: match spreadsheet columns to Wikidata properties using local reference tables, with fuzzy suggestions.
- Project constants: apply fixed statements (e.g., instance of (P31) = village (Q532)) to every uploaded item.
- Secure bot-password and OAuth authentication (credentials encrypted via Windows DPAPI).
- Dry-run preview with validation before any write.
- Live upload via WikidataIntegrator, with configurable delay between rows to respect rate limits.
- Persistent settings (edit summary, upload delay) stored in the Windows registry.
- **Lazy loading** for large datasets: only the first 500 rows are shown initially; full data is loaded in the background only when needed for dry-run or upload.
- **In-app reference table editing**: modify Wikidata property mappings and project constants directly from the application.
- **Duplicate detection**: identify and optionally skip rows that appear to already exist on Wikidata, and detect duplicates within the input batch.

## Requirements

- Windows 10 or later (for running the packaged `.exe`).
- Python 3.10 or later (for development and building from source).
- Dependencies listed in `requirements.txt`.
  - **Note:** PyInstaller is required for building the executable but is **not** included in `requirements.txt` (to keep runtime dependencies minimal). Install it separately with `pip install pyinstaller`.

## Setup (Development)

1. Clone or download this repository.
2. Install dependencies:

   ```
   pip install -r requirements.txt
   pip install pyinstaller   # only if you plan to build the exe
   ```

3. Run the application:

   ```
   python main.py
   ```

## Building the Windows Executable

A single, reproducible build is defined in `requirements-lock.txt` and `build.py` at the repository root. Do not use any other build scripts; they are obsolete.

1. Install the locked build dependencies:

   ```
   pip install -r requirements-lock.txt
   ```

2. Run the build script:

   ```
   python build.py
   ```

   This runs PyInstaller with `--onefile` and `--windowed`, producing a standalone executable. The build script:
   - Enforces that it is run on Windows.
   - Assumes all dependencies (including PyInstaller) are already installed via `pip install -r requirements-lock.txt`.
   - Collects all required packages via `--collect-all`.
   - Verifies that `dist/WikiDataBatchUploader.exe` exists and is non-empty.
   - Performs a startup smoke test: launches the exe, waits 5 seconds, and fails the build if it exits early.

   The CI workflow (`.github/workflows/build.yml`) performs an additional 10-second smoke test after building.

3. The executable will be located at `dist/WikiDataBatchUploader.exe`.

You can distribute this single `.exe` file. No Python installation is required on the target machine.

### Debug Console Build

For troubleshooting crashes or diagnosing startup errors, build a debug version that opens a console window and displays stdout/stderr:

```
python build.py --console
```

The resulting executable will be named `dist/WikiDataBatchUploader_debug.exe`. This version is not windowed, so you can see error messages that might be hidden in the standard windowed build. All heavy operations (dry-run, upload, duplicate check) run on background worker threads, and all UI updates from those threads are queued safely to the main GUI thread, ensuring thread safety and responsiveness.

## Usage

1. Launch `WikiDataBatchUploader.exe`.
2. From the **File** menu, choose **Open Folder...** (Ctrl+O). Select a folder containing your data sheets and/or images.
3. Files appear in the left sidebar. Click a file:
   - **Tabular files (`.xlsx`, `.csv`)**: Opens the preview and mapping view.
     - The top pane shows a read-only preview of the first 500 rows (see [Lazy Loading](#lazy-loading)).
     - The bottom pane contains the mapping panel and upload controls.
     - In the mapping panel, each column has a dropdown to select a Wikidata property. Use **Suggest Mappings** to auto-fill based on fuzzy matching against the property labels in `wikidata_properties.xlsx`.
     - Project constants are displayed read-only.
     - You can mark columns as **duplicate keys** by checking the checkbox in the mapping table. These columns are used to detect whether a row already exists on Wikidata (see [Duplicate Detection](#duplicate-detection)).
   - **Images**: Displays the image and a table of extracted metadata (EXIF, GPS, IPTC, etc.).
4. To upload:
   - Map at least one column to a property.
   - (Optional) Click **Check Existing Items** to scan the dataset against Wikidata for potential duplicates using the columns you marked as duplicate keys. The app will highlight rows that appear to already exist.
   - Click **Dry Run** to see a summary of what would be uploaded and any validation warnings. The first time you run a dry-run on a large dataset, the app will load the full data in the background; a status message will indicate this.
   - If the dry-run looks good, click **Upload**. You will be prompted for bot credentials (first time) and an edit summary.
   - The upload runs in the background; progress is shown in the status label. Wait for completion.

## Lazy Loading

To keep the interface responsive, the application only loads a **preview** of the first **500 rows** when you select a spreadsheet. This is enough for mapping columns and exploring structure without waiting for massive files.

When you click **Dry Run**, **Check Existing Items**, or **Upload**, the application automatically loads the **entire dataset** in the background. You will see a "Loading full data..." status message and the buttons will be temporarily disabled. Once complete, the requested operation proceeds automatically.

This behavior is transparent: the preview data is used solely for display and mapping; all validation and upload operations use the full data.

## Duplicate Detection

The application helps you avoid creating duplicate items on Wikidata in two ways:

### Within-Batch Duplicate Detection

Before uploading, the app automatically checks the dataset for rows that have identical values across all mapped columns. If such duplicates exist, you will see a warning dialog showing the number of duplicate groups and affected rows. You can choose to continue (all rows will be uploaded as separate items) or abort to correct the data.

### Existing Item Check

You can use the **Check Existing Items** button to query Wikidata for items that may already represent the data in your rows. This feature requires you to mark one or more columns as **duplicate keys** in the mapping table (via checkboxes). When you run the check:

- The app builds a SPARQL query using the values from those columns and their mapped Wikidata properties.
- It runs the query against Wikidata's SPARQL endpoint.
- Rows that match existing items are recorded.
- After the check, when you click **Upload**, you will be asked whether to skip these rows. You can choose to skip them (recommended) or upload them anyway.

**Important:** The duplicate key columns should contain values that are both distinctive and stable for a given entity (e.g., a unique identifier, a combination of name and location). Using poorly chosen keys may result in false positives.

## AI-Powered Schema Mapping

The application can optionally use a remote AI endpoint to suggest column-to-property mappings based on a sample of your data. This is useful when local fuzzy matching is insufficient or the schema is ambiguous.

### How It Works

1. When you click **AI Suggest** in the mapping panel, the app sends the column headers and up to **5 sample rows** to a configurable endpoint.
2. The endpoint analyzes the data context and returns a JSON response:
   ```json
   {
     "mappings": [
       {"column": "name", "label": "inception"},
       {"column": "country", "label": "country"}
     ]
   }
   ```
3. The app then matches each returned label against the local `wikidata_properties.xlsx` to obtain the property ID, and updates the mapping dropdowns accordingly.
4. If the endpoint is not configured or the request fails, the app automatically falls back to local fuzzy mapping.

### Configuration

The endpoint URL and optional API key are read from environment variables:

- `MORPHEUS_AI_ENDPOINT` — full URL of the AI mapping endpoint (e.g., `https://morpheus.nz/api/schema`)
- `MORPHEUS_AI_API_KEY` — (optional) bearer token for authentication

Set these variables before launching the application. On Windows, you can set them in the command prompt:

```
set MORPHEUS_AI_ENDPOINT=https://morpheus.nz/api/schema
set MORPHEUS_AI_API_KEY=your_api_key_here
```

If the endpoint is not set, the **AI Suggest** button will show a warning and use the local mapping instead.

**Note:** These variables are read only at the time you click the button. To change them, restart the application with the new environment.

### Using Google Gemini (Free)

You can use Google Gemini instead of the Morpheus endpoint for AI schema mapping. This is useful while the Morpheus endpoint is not yet available, and Gemini offers a free tier.

To enable Gemini:

1. Obtain a Gemini API key from [Google AI Studio](https://aistudio.google.com/).
2. Set the environment variable `GEMINI_API_KEY` to your key.
   - If you also set `GEMINI_MODEL`, you can override the default model. The default is `gemini-3.5-flash`.
3. Optionally, if you have no `GEMINI_API_KEY` but have set `GEMINI_MODEL`, the app will fall back to `MORPHEUS_AI_API_KEY` (if set).
4. When `GEMINI_API_KEY` is present, the Morpheus endpoint (`MORPHEUS_AI_ENDPOINT`) is ignored.

Gemini responses are converted into the same column-to-property mapping format. If the request fails or returns no usable mappings, the app falls back to local fuzzy suggestion.

**Warning:** Keep your API key secret. Do not commit it to version control.

## Reference Tables

The application uses two Excel files stored in `reference_tables/`:

- `wikidata_properties.xlsx` — columns: `property_id`, `label`. Example: `P571`, `inception`.
- `project_constants.xlsx` — columns: `property_id`, `value`. Example: `P31`, `Q532` (instance of village).

When you run the app, it checks for these files. If they are missing, sample files are generated automatically.

**Location:**
- **Development mode**: In the project root, alongside `main.py`.
- **Packaged `.exe` mode**: In a user-writable directory:
  - Windows: `%APPDATA%\WikidataBatchUploader\reference_tables`
  - (The base folder `%APPDATA%\WikidataBatchUploader` is created automatically.)
  This location ensures that changes you make to the reference tables persist between runs and do not require administrator rights.

You can edit these files with Excel to customize property labels and project constants.

**In-App Editing:**
The application also provides a built-in editor. From the **File** menu, choose **Edit Reference Tables...**. A dialog opens with two tabs: **Wikidata Properties** and **Project Constants**. You can add, delete, and modify rows directly. When you save, the changes are written to the Excel files, and the mapping view is refreshed to reflect the new property list and constants immediately.

## Credentials & Security

The application supports two authentication methods: **bot passwords** and **OAuth 1.0a**.

### Bot Password (Basic)

- Create a bot password at [Special:BotPasswords](https://www.wikidata.org/wiki/Special:BotPasswords).
  - Grant: Edit existing pages; Create, edit, and move pages; High-volume editing (if needed).
- The bot username will look like `YourUsername@BotName`.
- Enter the bot username and bot password in the login dialog when prompted.

### OAuth 1.0a (Recommended for High-Volume Bots)

- Register an OAuth consumer at [Special:OAuthConsumerRegistration](https://www.wikidata.org/wiki/Special:OAuthConsumerRegistration).
- Choose "This consumer is for use only by myself" unless you are building a multi-user tool.
- After registration, you will receive four values: **Consumer key**, **Consumer secret**, **Access token**, and **Access secret**.
- In the login dialog, check **Use OAuth 1.0a** and enter those four values.

Credentials are entered only when you initiate an upload. They are encrypted using Windows DPAPI and stored securely in the user's AppData directory. They are not stored in plaintext.

## Validation & Rate Limiting

Before any live upload, the app validates:

- All mapped property IDs exist in the local property reference table.
- Project constant values are valid QIDs (e.g., `Q532`).
- No mapped column contains empty cells in any row.

Warnings and errors are shown during dry-run. Fix any missing values or invalid constants before uploading.

To avoid overloading Wikidata, you can set a delay between row uploads (Settings menu). A delay of 1–5 seconds is recommended for large batches.

The app also respects Wikidata's maxlag parameter. You can set the maximum number of seconds of lag you are willing to accept in the Settings menu (default: 5 seconds). If the server reports a higher lag, the app will automatically retry up to 3 times, waiting 10 seconds between attempts, before reporting an error. The maxlag value is now correctly passed to the Wikidata API via the library's configuration, ensuring the setting takes effect. This helps avoid overwhelming the Wikidata servers during periods of high load.

## Troubleshooting

**The `.exe` doesn't start or crashes instantly**
- Ensure your system has the latest Visual C++ Redistributable (if unsure, install it).
- Check that your data files are not corrupted.
- Run the development version (`python main.py`) to see error output.
- If the crash persists, build the debug console version (`python build.py --console`) and run `dist/WikiDataBatchUploader_debug.exe` from a command prompt to view error messages.

**Login fails**
- Verify you are using the bot username and bot password, not your regular credentials.
- Ensure your bot has the necessary rights (edit existing pages, create/edit/move pages).
- Check that your system clock is correct (OAuth token validation depends on time).

**Upload errors**
- Make sure all mapped columns have no empty values.
- Increase the upload delay in Settings.
- Check that the property IDs and QIDs exist on Wikidata.

**Reference tables are not found / not editable**
- In the packaged app, the tables are under `%APPDATA%\WikidataBatchUploader\reference_tables`. They are created automatically on first run. If you delete them, they are recreated with defaults.
- You can edit them in-app via **File > Edit Reference Tables...** or by opening the Excel files directly.

**Large datasets appear slow**
- The preview only shows the first 500 rows. Dry-run and upload operations load the full dataset, which may take time for very large files.

**Existing Item Check returns no results**
- Ensure you have marked at least one column as a duplicate key in the mapping table.
- The SPARQL query may return no results if the values do not match any item's statements exactly. Try using a more distinctive combination of columns.
- Network issues or Wikidata SPARQL endpoint downtime can prevent the check from completing; try again later.

## License

Your own. This is your tool. Use it responsibly.
