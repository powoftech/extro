# Extro

Extro is an unofficial command-line tool for people who use O'Reilly Learning and want a local, personal workflow for their books.

It helps you find books, save local snapshots, check what you have, and convert a saved snapshot into a Send to Kindle-compatible EPUB.

## Important Note

Extro is not affiliated with, endorsed by, or supported by O'Reilly Media.

Use it only with books you can already access through your own O'Reilly Learning account. Extro is meant for personal library management, not for sharing, redistributing, or bypassing access rules.

This is an early project. Expect the workflow and output to improve over time.

## Prerequisites

- Python 3.14 or newer.
- `uv` for setup and running commands.
- Firefox installed.
- A Firefox profile that is already signed in to O'Reilly Learning.

## Install From Source

Clone the repository, enter the project directory, and install the project environment:

```powershell
uv sync
```

Run Extro from the project directory:

```powershell
uv run extro --help
```

Show the installed version:

```powershell
uv run extro --version
```

## First Run

Start by choosing the Firefox profile Extro should use:

```powershell
uv run extro config
```

Extro will show the Firefox profiles it can find and ask you to select one. Choose the profile that is already signed in to O'Reilly Learning.

## Everyday Workflow

Search for a book:

```powershell
uv run extro search "<keyword>"
```

Download a book snapshot:

```powershell
uv run extro download <book-url-or-id>
```

Convert a downloaded snapshot to EPUB:

```powershell
uv run extro convert <book-url-or-id>
```

Check what is saved locally:

```powershell
uv run extro status
```

Verify saved files:

```powershell
uv run extro verify
```

Delete snapshots for one book:

```powershell
uv run extro delete <book-url-or-id>
```

Reset all local Extro data:

```powershell
uv run extro reset
```

## Command Reference

### `config`

Selects the Firefox profile Extro should use.

Run this before downloading. You can run it again later if you switch Firefox profiles.

```powershell
uv run extro config
```

### `search`

Searches English books on O'Reilly Learning and prints matching titles, authors, publishers, ISBNs, and identifiers.

```powershell
uv run extro search "<keyword>"
```

Useful options:

```powershell
uv run extro search "<keyword>" --field title
uv run extro search "<keyword>" --field authors
uv run extro search "<keyword>" --field publishers
uv run extro search "<keyword>" --field isbn
uv run extro search "<keyword>" --sort popularity --limit 20
uv run extro search "<keyword>" --page 2
```

### `download`

Downloads a local snapshot of a book you can access. If a download was interrupted, running the command again resumes progress.

```powershell
uv run extro download <book-url-or-id>
```

The argument can be an O'Reilly book URL, URN, or identifier.

### `convert`

Converts a completed local snapshot to an EPUB file. If more than one snapshot is available, Extro asks which one to convert.

```powershell
uv run extro convert <book-url-or-id>
```

To inspect Kindle-related hidden content issues without writing an EPUB:

```powershell
uv run extro convert <book-url-or-id> --audit-hidden
```

### `status`

Shows the books and snapshots saved locally.

```powershell
uv run extro status
```

Show one book:

```powershell
uv run extro status <book-url-or-id>
```

Page through the list:

```powershell
uv run extro status --limit 20 --page 2
```

### `verify`

Checks whether downloaded files are still present and unchanged.

```powershell
uv run extro verify
```

Check one book:

```powershell
uv run extro verify <book-url-or-id>
```

### `delete`

Interactively deletes one or more snapshots for a book. If converted files exist for the selected snapshots, Extro asks whether to delete those too.

```powershell
uv run extro delete <book-url-or-id>
```

### `reset`

Deletes all local Extro books, snapshots, and downloaded assets, then recreates an empty local library.

```powershell
uv run extro reset
```

This command asks for confirmation before deleting anything.

### `--version`

Prints the Extro version.

```powershell
uv run extro --version
```

## Data Locations

Extro stores its files in the normal application folders for your operating system.

- Configuration: the selected Firefox profile.
- Local library: saved book records and downloaded snapshots.
- Exports: converted EPUB files.

Use `extro status`, `extro delete`, and `extro reset` to manage this data instead of editing files by hand.

## Troubleshooting

### Extro cannot find Firefox

Install Firefox and open it at least once so it creates a profile.

### Extro cannot access O'Reilly Learning

Open Firefox, sign in to O'Reilly Learning, then run:

```powershell
uv run extro config
```

Choose the signed-in profile.

### A download fails

Run the same download command again. Extro is designed to resume incomplete downloads.

```powershell
uv run extro download <book-url-or-id>
```

### The EPUB already exists

When converting, Extro asks before overwriting an existing EPUB.

### Kindle conversion looks suspicious

Run the hidden content audit:

```powershell
uv run extro convert <book-url-or-id> --audit-hidden
```

This reports potential hidden text issues without creating a new EPUB.

### You want to start over

Use reset:

```powershell
uv run extro reset
```

Read the confirmation prompt carefully. This removes the local Extro library.

## Contributor Notes

Use `uv` for Python, environments, and packages:

```powershell
uv sync
```

Run checks before sending changes:

```powershell
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest
```

Keep the README focused on what users can do with Extro. Detailed implementation notes belong in code, tests, or developer documentation.

## License

Extro is released under the MIT License. See [LICENSE](LICENSE).
