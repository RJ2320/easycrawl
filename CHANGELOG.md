# Changelog

## 0.3.13

- Unify toolbar and right-click Layout menus, group row operations and remove duplicate commands.
- Route music and logo grid editing to their dedicated editors instead of the generic Side by side dialog.
- Support populated Roles / names overrides with normal two-column alignment, even inside music sections.
- Separate Recent projects from Recent source sheets with friendly labels and independent history limits.
- Add Match spreadsheet columns for Special thanks, preserving left/right pairs, empty cells and centered middle-column entries.
- Keep wrapping, hidden source coordinates, saving and undo consistent with spreadsheet-matched name grids.

## 0.3.12

- Ignore hidden worksheet rows without adding text or spacing, while preserving visible blank rows and source coordinates.
- Save hidden-row metadata with projects and track it through edits, undo and source revisions.
- Recover hidden-row visibility for older projects when a matching cached workbook is available.
- Add Center credit name for standalone names, retaining normal name typography and line spacing across source-column changes.
- Treat Google Sheets as the master for credit text by default; include capitalization and previously skipped differences on refresh.
- Label capitalization-only changes separately in revision review and retain the optional three-way merge mode.
- Protect assigned EasyCrawl logo rows when they correspond to source logo placeholders.

## 0.3.11

- Fix Move earlier / Move later so logo order updates immediately and the selection survives refreshes.
- Add drag-and-drop reordering in the Logos list, including multiple selected logos.
- Save ordering with the project and support undo/redo; creating a grid and making the first move are one undo step.
- Keep canvas dragging for manual positioning separate from list reordering.

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
