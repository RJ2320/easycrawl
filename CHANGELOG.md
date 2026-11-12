# Changelog

## Unreleased

- Explicitly read and write project files as UTF-8, accepting UTF-8 byte-order marks and preserving older ASCII-safe projects.
- Flag possible garbled text and unreadable replacement characters; offer reversible encoding corrections for explicit review.
- Add a filterable issue review with severity, type, section and exact cell locations, plus undoable suggested corrections.
- Count informational notes separately from warnings.

## 0.3.21

- Simplify the workspace with top navigation for Look, Timing and Export settings, compact text tools, and consolidated menus.
- Display section headings and logo blocks across the spreadsheet row without moving source cells; add subtle row-type colors.
- Replace the logo block dropdown with a collapsible numbered thumbnail list and block count.
- Add contextual crawl viewing, alignment and distribution icons, exact pair spacing and pair centering; keep logo adjustments above the viewer.
- Make logo spacing consistent while retaining explicitly marked spacing rows; prevent following names-only and music rows from overlapping.
- Cache repeated font measurements to reduce layout rebuild delays without changing rendered geometry.
- Clarify source importing, keep recent projects, and move import history beside the source name.

## 0.3.20

- Preserve fractional horizontal font advances so music labels and names retain exact spacing across platforms.
- Fix the Linux release check that blocked installer builds when a fallback font used fractional character widths.

## 0.3.19

- Add Face center for names-only rows, using the normal role/name positions while retaining name typography on both sides.
- Recover the full Special thanks section when a names-only layout has separated its names from the heading.
- Add a one-click role/name alignment preset in Special thanks settings.
- Mark selected empty rows as explicit visible spacing, with a highlighted row and a separate gap for every marked row.
- Save spacing marks with projects and preserve them through undo, row edits and source updates without hiding populated credits.

## 0.3.18

- Import EPS logos through artwork pickers and My logos with automatic high-resolution PNG conversion and original EPS retention.
- Detect a separately installed Ghostscript renderer for the initial conversion; cached PNGs work independently afterward.
- Add per-cell automatic text wrapping and respect manual line breaks in headings and role titles.
- Target right-click actions at the clicked cell, preserve clicks within a multi-cell selection and hide unavailable layout choices.
- Add independent left and right Special thanks column alignment, including alignment toward the middle gap.

## 0.3.17

- Show the actual parsed row type beside spreadsheet row numbers, with details on hover.
- Distinguish manually marked rows and local text styling, and allow row labels to be hidden under Layout.
- Make mixed-case section headings follow the section-header style instead of the song-title style.
- Add a Section heading layout override for single-cell heading rows in any credit column.
- Open the Logos page directly from any logo block and select that row's artwork, including blocks without a grid.
- Clarify Look font groups with their normal positions, examples and the difference between thanks headings and thanks names.

## 0.3.16

- Add a font color picker with RGB and hex entry to manual text formatting.
- Preserve per-cell colors in project files, undo, source updates, preview and color exports.
- Let individual text colors return to the section default without removing other styling.

## 0.3.15

- Add left, center and right alignment for names-only rows, retaining shared name typography for paired names.
- Add per-cell font, size, line spacing, alignment, bold, italic and uppercase overrides without changing source-sheet text or shared Look settings.
- Add direct heading font and styling controls to the Special thanks dialog.
- Apply manual styling to preview, exports, wrapping and layout warnings, with a reset to section defaults.
- Preserve formatting through project saving, undo, row edits and source-sheet updates.

## 0.3.14

- Remove unused hidden export and legacy logo-slot controls from Export settings.
- Keep CSV text export in one location under Export and simplify Rows review tools.
- Make the export menu label follow the chosen codec or PNG sequence format.
- Enable Cancel Export only during an active export and disable it after cancellation is requested.
- Keep the visible preview and Logos inspectors synchronized without legacy hidden controls.

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
