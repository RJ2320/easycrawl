# Changelog

## 0.3.10

- Remove selected logos and placeholders from the Logos workspace, with undo and shared-logo protection.
- Keep artwork files when removing logo slots, clear empty logo grids and refresh stale canvas items.
- Rename logo controls to Replace selected logo, Add logo, Remove logo, Logo library and Show locations.
- Make replacement of placeholder artwork undoable.
- Simplify the Credits toolbar to Rows, Layout, Side by side and the expand icon.
- Move Music and Logo library into Layout; move review and export options into Rows.

## 0.3.9

- Add a searchable logo library with verified official-source downloads, artwork variants and offline caching.
- Save personal and current-project logos privately for reuse, with searchable names and tags.
- Convert selected spreadsheet cells into logo blocks, with optional file or library artwork and undo.
- Fit thanks columns around their names; add per-section column gaps and across-row name order.
- Keep similar-name warnings within a section instead of comparing different departments.
- Preserve saved-project artwork when newer library versions are downloaded or personal entries are removed.

## 0.3.8

- Mark music song blocks, legal text and multiple independent Special thanks sections explicitly.
- Choose stacked or multi-column music layouts with individual song boundaries and spacing.
- Simplify Look controls with descriptive labels, Advanced settings and individual reset buttons.
- Use consistent spacing below section headings by optionally ignoring following blank rows.
- Wrap long and multiline thanks entries without overlapping subsequent rows.
- Bring thanks columns closer with a 55% default width and adjustable per-section widths.
- Preserve section settings through saving, undo and row insertions/deletions.

## 0.3.7

- Preserve Google Sheets links when reopening saved projects and enable Watch/Refresh controls immediately.
- Stop watching the previous Google Sheet when starting a blank project.
- Ignore background-check results from a different Google Sheet after switching sources.

## 0.3.6

- Fixed preview failure after importing credits with unassigned logo artwork.
- Added a Show all rows option to the import preview and clarified that its initial 80-row display is not an import limit.
- Added optional 2.39:1, 1.85:1 and 2.00:1 preview framing guides, plus an 80% title-safe guide. Guides do not appear in exports.
- Updated the Mac release runner to macOS 15.
