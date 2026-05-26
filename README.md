# Extro

Download O'Reilly Learning books and convert local snapshots to EPUB from the command line.

Extro is an unofficial command-line tool for managing a local O'Reilly Learning reading workflow. It can search O'Reilly Learning, download resumable local book snapshots, track downloaded files in SQLite, verify local file integrity, and convert completed snapshots to Send to Kindle-compatible EPUB files.

Extro authenticates by reading cookies from a Firefox profile you choose during configuration. It stores only local application data on your machine: configuration, a local database, downloaded snapshots, and converted exports.

## Table of Contents

- [Security](#security)
- [Background](#background)
- [Install](#install)
  - [Dependencies](#dependencies)
- [Usage](#usage)
  - [CLI](#cli)
- [Data Storage](#data-storage)
- [Development](#development)
- [Contributing](#contributing)
- [License](#license)

## Security

Use Extro only with O'Reilly Learning content that you are authorized to access through your own account or organization. Extro uses your selected Firefox profile's existing authenticated session; it is not a way to bypass access controls.

Downloaded snapshots and exported EPUB files are your responsibility. Handle them according to the applicable O'Reilly Learning, account, organization, and content license terms.

## Background

O'Reilly Learning is useful for reading technical books, but a browser-only workflow is awkward when you want local progress visibility, resumable downloads, file integrity checks, or a personal EPUB export for compatible readers. Extro provides a local CLI workflow around those tasks while keeping state in a platform-managed application directory.

The project is built as a Python CLI with Typer and Rich. It uses Firefox profile cookies for authenticated requests, SQLAlchemy and Alembic for the local SQLite library, and a local EPUB builder for completed book snapshots.

## Install

Clone the repository and install the project environment with `uv`:

```sh
git clone https://github.com/powoftech/extro.git
cd extro
uv sync
```

Confirm the CLI runs:

```sh
uv run extro --help
uv run extro --version
```

### Dependencies

Extro requires:

- Python 3.14 or newer.
- `uv` for Python version, environment, and package management.
- Firefox installed and opened at least once.
- A Firefox profile signed in to O'Reilly Learning.
- Authorized access to the O'Reilly Learning books you use with Extro.

## Usage

Run configuration first so Extro knows which Firefox profile to read:

```sh
uv run extro config
```

After that, the normal workflow is to search, download, convert, and verify:

```sh
uv run extro search "python" --limit 5
uv run extro download <identifier-or-url>
uv run extro convert <identifier-or-url>
uv run extro verify
```

The book argument accepted by download, convert, status, verify, and delete commands can be an O'Reilly book identifier, URN, or URL.

### CLI

`config` selects and saves the Firefox profile Extro should use:

```sh
uv run extro config
```

`search` searches English books on O'Reilly Learning:

```sh
uv run extro search "python" --field title --sort popularity --limit 10
uv run extro search "fluent python" --page 2
```

Supported search fields are `title`, `publishers`, `authors`, and `isbn`. Supported sort values are `relevance`, `popularity`, `date_added`, `publication_date`, `average_rating`, `title`, and `duration`.

`download` downloads or resumes a local snapshot:

```sh
uv run extro download <identifier-or-url>
```

`convert` converts a completed snapshot to EPUB. If more than one completed snapshot is available, Extro asks which one to convert:

```sh
uv run extro convert <identifier-or-url>
```

`status` shows downloaded books and snapshots:

```sh
uv run extro status
uv run extro status <identifier-or-url>
uv run extro status --limit 20 --page 2
```

`verify` checks stored SHA-256 hashes and read-only file protection:

```sh
uv run extro verify
uv run extro verify <identifier-or-url>
```

`delete` interactively removes selected snapshots for one book. If converted files exist for the selected snapshots, Extro asks whether to remove those exports too:

```sh
uv run extro delete <identifier-or-url>
```

`reset` deletes the local Extro library and downloaded assets, then recreates an empty database:

```sh
uv run extro reset
```

Read the confirmation prompt carefully before using `reset`.

## Data Storage

Extro stores application data in the standard per-user application directories for your operating system, as resolved by `platformdirs`.

- Configuration stores the selected Firefox profile in `config.json`.
- Local library state is stored in `extro.db`.
- Downloaded book snapshots are stored under `downloads/`.
- Converted EPUB files are stored under `exports/`.

Use `extro status`, `extro verify`, `extro delete`, and `extro reset` to inspect or manage local Extro data instead of editing these files by hand.

## Development

Use `uv` for Python versions, virtual environments, and packages:

```sh
uv sync --dev
```

Run the project checks before sending changes:

```sh
uv run pytest
uv run pyright
uv run ruff check .
uv run ruff format --check .
```

Database schema changes should use SQLAlchemy models and Alembic migrations.

## Contributing

Questions, bug reports, and feature requests should be opened in the [GitHub issue tracker](https://github.com/powoftech/extro/issues).

Focused pull requests are welcome. Please include relevant tests and make sure `pytest`, `pyright`, `ruff check`, and `ruff format --check` pass before submitting.

## License

MIT © 2026 Phuong Dang. See [LICENSE](LICENSE).
