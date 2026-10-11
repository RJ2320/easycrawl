# EasyCrawl development guide

EasyCrawl turns a credits spreadsheet into a pixel-accurate scrolling movie.
The checked-in sample credits are fictional. Production sheets, artwork, client
references, and project-specific specifications must stay outside this repository.

## Design principles

- Keep Python layout and rendering as the source of truth for pixels.
- Use an integer number of pixels per frame; adjust spacing to fit runtime.
- Flag credit problems for human review rather than making billing decisions.
- Preserve source spreadsheets and store edits in the saved project.
- Keep preview acceleration separate from final movie rendering.

## Development

Install `.[ui,dev]` into a virtual environment and run `python -m pytest`.
Use `examples/sample_crawl.csv` for development and demonstrations.
See README.md for installation, export, packaging, and release instructions.

## Distribution

Fonts are installed separately. FFmpeg is bundled during release builds.
Do not include production data or studio templates in release downloads.
