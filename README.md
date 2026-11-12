# Crawl

Turns a credits sheet into a finished end-crawl movie in one step:
sheet in, ProRes out, scrolling at an exact integer number of pixels per frame.

See [HANDOFF.md](HANDOFF.md) for the development guide and design principles.

## Download the app

Ready-made apps for Mac (Apple silicon) and Windows are on the
[Releases page](https://github.com/RJ2320/easycrawl/releases). On Windows, download the
`EasyCrawl-Setup-<version>-windows.exe` installer: it installs the app for your account and
creates a Start menu shortcut, with an optional desktop shortcut. Run a newer installer
to upgrade the same installation; uninstall through Windows Settings. On Mac, open
`EasyCrawl-<version>-mac.dmg` and drag EasyCrawl to Applications. Python and ffmpeg are included.

Packaged apps check for newer stable releases at launch. The update notice opens the
matching Windows installer or Mac disk-image download; installation is your choice. The Mac app isn't notarized with Apple, so the first launch is right-click → Open
(if macOS calls it "damaged", run `xattr -cr /Applications/EasyCrawl.app` once). Fonts are not
bundled: the fonts a project uses must be installed on the machine; the default look falls back
to the system's sans-serif where Helvetica Neue is missing.

A new release is built by pushing a version tag (`git tag v0.2.0 && git push origin v0.2.0`), or
by running the Build workflow by hand on GitHub. The bundled ffmpeg is a GPL build (it includes
x264), which is fine to use and to share inside a studio; it matters if the app itself is ever
published under a non-GPL licence.

To build locally instead: `pip install pyinstaller`, then `python packaging/fetch_ffmpeg.py`,
`python packaging/make_icon.py`, `pyinstaller packaging/easycrawl.spec`. The app's `--selftest`
flag reports whether it can find ffmpeg and fonts.

## Install from source

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[ui,dev]"
```

Python 3.9+. The engine needs Pillow, numpy, openpyxl and fonttools; the desktop app adds PySide6.
Movie export needs **ffmpeg** on the PATH (`brew install ffmpeg`), or `pip install imageio-ffmpeg`.

## Use

**Desktop app**

```bash
.venv/bin/crawl-ui examples/sample_crawl.csv
```

Run it with no argument for the empty state, then open a sheet (`.csv` or `.xlsx`), drop one on
the window, paste a Google Sheets link, or **Start blank**. The tabs follow the work: Credits → Look → Timing →
Export, with the preview on the right and the **Export** button always in the header.

- **Credits** — the sheet's B/C/D cells, edited like a spreadsheet. Edits are stored in the
  `.crawl.json` project; the original file is never changed.

  | Do this | To |
  |---|---|
  | Type | replace the cell |
  | Enter, F2 or double-click | edit in place |
  | Enter / Shift+Enter | commit and move down / up |
  | Tab / Shift+Tab | commit and move right / left |
  | Alt+Enter (or Ctrl+Enter) | new line inside the cell — one name per line |
  | Ctrl+I while editing | italicise the selected words (stored as `*italic*`) |
  | Delete | clear the selected cells |
  | Ctrl+C / X / V | copy, cut, paste ranges, to and from Excel or Sheets; a paste past the last row grows the sheet, and one value pasted into a selection fills it |
  | Ctrl+Z / Shift+Ctrl+Z | undo / redo (credits, layout, arrangements and logo placement) |
  | Right-click | cut/copy/paste, insert or delete as many rows as are selected, layout, arrangements, logos |
  | Ctrl+F | find |

  Clicking or arrowing to a row pauses the preview and centres it there (blank rows use the
  nearest credit); turn that off under **···**. Section headers are bold and logo rows blue, so
  the structure reads at a glance.

  **Problems** — cells with a finding are outlined red (must fix) or amber (worth a look), with the
  reason in the tooltip. The chip beside Find shows the counts; click it to show only the rows
  with problems, and use ‹ › to step through them. Editing a cell clears that row's findings at once.

  **Dismissing** — once you've checked a finding, **Dismiss** (in the bar that shows it, on the
  right-click menu, or Ctrl+D) stops it being flagged so the list dwindles as you work through
  it. A dismissal is about the content, not the row: it holds when rows move and lapses if that
  text changes. Dismissed errors no longer block export. **··· → Restore dismissed problems**
  brings them all back; they save with the project.

  **Layout** overrides how selected column-B-only rows are set: *Roles* puts each in the left
  column with the name column empty until names arrive (and stops the "has no names" errors);
  *List in columns* forces a list even for a short run; *Centred lines* sets one centred line per
  row; *Automatic* clears it. Overridden rows carry a grey bar at the left.

  **Layout → Arrange sections in columns…** sets two or more groups next to each other. Select rows across the groups
  (blank rows separate them), choose 2–6 columns, a gap, alignment and a label. A blue outline with
  a labelled band marks the arrangement; put the cursor inside it to edit the arrangement from Layout.
  Blocks fill left to right and align at the top; an incomplete last row is centred.

  **Layout → Logo block…** converts selected cells into logo entries in their existing
  rows. Use the cell text as the logo name, or choose a name for an empty cell. Leave
  a placeholder, assign a file, or choose artwork from the logo library. Select multiple
  entries to make several placeholders; entries on the same row appear side by side.
  Other populated cells on a row must be included so neighboring credits are not lost.
  Conversion supports undo and saves with the project.

  **Layout → Logo library…** opens the searchable logo library (also **Logos → Logo library…**).
  Search **Official sources** for the starter catalog: Panavision, Millennium DXL,
  Filmed in Panavision, Panalux, LEE Filters, Canon and TCS download directly from
  their owners, with artwork variants and usage notes. Kodak, Dolby, Cinema EOS and
  SAG-AFTRA entries link to their official resources when manual artwork or approval
  is needed. Use **Open official source / guidelines** to check current requirements.

  **Import my logos…** copies artwork into a private local **My logos** collection,
  available in every project. **Save project logos to My logos** saves the current
  project's assigned artwork for reuse. Names and tags are searchable. Nothing is
  uploaded. Downloads are cached for offline use; checking for newer artwork creates
  a separate version and never changes logos already used in a saved project.
  Removing a personal entry hides it from the library while retaining files needed
  by existing projects. Original source files can be moved after importing.

  Choose a logo/variant and **Add to credits** to insert artwork as a new row, side by side; select an existing logo row first to
  append to it. You can also drop image files on the window. Logos are measured by their artwork,
  not their file — transparent or black margins are trimmed — so resolution and canvas size don't
  affect how big a logo appears. **Look → Show advanced settings → Balance different logo shapes** sets how different
  shapes are sized against each other: 0 % gives every logo the same height (wide wordmarks
  dominate), 100 % the same area. A row wider than 80 % of the frame shrinks to fit.

  **Placing a logo by hand** — click it in the preview, then drag (Shift locks to one axis, Alt
  turns off snapping). It snaps to its automatic spot, the frame's centre line and the centres and
  edges of the other logos, with guide lines. The controls above the viewer include X/Y offset,
  Size, **Invert** (for a dark logo on the black crawl) and **Reset**.

  **Greyscale** — select a logo and tick **Greyscale** beside Invert above the viewer. This removes color in the preview
  and final export while preserving transparency. Turn it off to restore the original color.

  **Levels** — the same inspector has **Black** and **White** points, applied after Invert.
  Raise Black until a not-quite-black background box disappears (**Auto** reads the level from
  the artwork's corners and sets it for you); lower White to brighten a dull logo. Once the
  background is crushed to black the logo is trimmed and sized by its artwork like any other.
  For a logo on a light background, tick Invert first, then Auto.

- **A sheet that doesn't follow the template** — credits belong in columns B–D. If text turns up
  elsewhere, import doesn't drop it silently: a cell on an otherwise empty row (legal text typed
  in column A, say) is moved into column B and becomes a normal row; a whole table that is one
  column over is read from where it is; text sitting *beside* real credits is left out. Each of
  these is a warning on its row, so you can see what was done and dismiss it once checked.

- **Import options** — when a workbook has several tabs, or the credits aren't where the
  template puts them, an import dialog asks before anything is read; **File → Import Options…**
  opens it for the current sheet at any time. It shows the cells as they are in the file with
  the chosen columns tinted, and says what the crawl would read from them.

  - **Worksheet** — pick the tab. The one named *Crawl* or *Credits* is preselected, otherwise
    the fullest one; a workbook with a single tab is never asked about.
  - **Columns** — which column holds the role, the centred heading and the names. Names spread
    across several columns (one per column instead of one per line) are read as a range,
    *D to F*, and stacked. **Find columns** goes back to the three columns with the most text.
  - **Start row** — skip title or notes rows at the top. Row numbers still match the sheet.

  The settings are saved in the project and used again for revisions. On the command line they
  are `--sheet`, `--columns B,C,D-F` and `--start-row`.

- **Explicit sections** — select rows in Credits and choose **Layout → Music…** to define song
  blocks without relying on quotation marks. Song boundaries can be split, merged or
  edited by row number. Choose stacked or 2–6-column layouts, alignment and spacing;
  **Music typography…** opens the shared song/label/name style controls under Look.
  **Return to automatic** removes the manual music markings without changing text.

  Under **Layout**, **Legal text** explicitly treats the selected text as legal copy,
  even when it is short or has no copyright marker. **Special thanks…** gives each
  selected thanks section an optional first-row heading, its own 1–6 name columns and
  **Maximum section width** (% of frame) and **Space between columns**. New layouts default to a compact 55% width;
  the reset arrow restores 55%. Saved shared widths remain unchanged until adjusted.
  Mark multiple thanks sections separately to give them different layouts. Markings
  save with the project, support undo, and shift when rows are inserted or deleted.

- **Google Sheets** — **File → Import Google Sheet…** (Ctrl+Shift+G), or drop or paste the link
  on the window. The sheet must be shared as *Anyone with the link* (Viewer is enough): the app
  downloads the whole workbook, every tab, and reads it like a file, so no Google sign-in is
  needed. The download is kept with the project (in its `_assets` folder once saved), so the
  project opens without a connection.

  - **File → Refresh from Google Sheet** (Ctrl+Shift+U) downloads it again and opens the
    revision review below, exactly as a revised file would.
  - **Watch Google Sheet for Changes** (on by default) checks every minute and shows a bar under
    the header when the sheet has changed, with **Review changes…**. Nothing is applied until you
    say so.
  - **Apply Google Sheet Changes Automatically** brings changes straight in while watching.
    Changes that touch rows you have also edited here are held back for review instead, so your
    edits are never overwritten silently.

  Sheets that aren't shared by link can't be read this way; download them as `.xlsx` instead.

- **Relink missing files** — **File → Relink Missing Files…** lists missing source spreadsheets
  and logo artwork. **Search folder…** searches subfolders too and selects unique filename
  matches. If several files share a name, choose the right one; use **Choose…** for renamed
  artwork. **Apply relinks** applies your reviewed choices together, preserving logo placement,
  size and tone settings. Unresolved files stay unchanged. Save the project to keep the new paths.

- **Export naming** — on the Export tab, **Add date and time to output names** appends local
  export time, such as `crawl_2026-10-07_14-30-05.mov`. **Use the next version number** looks
  at files already in the output folder and selects `v001`, `v002`, and so on. Both can be used
  together: `crawl_v002_2026-10-07_14-30-05.mov`. The movie, PNG sequence, report and optional
  Fusion files from an export share the same version and timestamp. These options save with
  the project; the base file name stays the same.

- **Version snapshots** — **File → Version Snapshots…** lets you save a named milestone,
  such as *Client review 1* or *Final approved*, and rename, delete or restore it later.
  Each snapshot captures the credits, look, timing, logo assignments and placement, import
  settings, revision baseline and export settings. **Save Project** keeps the snapshots inside
  the `.crawl.json` file; they also travel with **Save Project As**.

  Restoring automatically creates a *Before restoring…* snapshot of your current work, so you
  can return to it. Restore refreshes all tabs and the preview, starts a new undo history, and
  pauses Google Sheet watching; turn watching back on when you're ready to bring in updates.
  Save the project after restoring to keep that version as the current one.

  Logo artwork and fonts remain external files. **Collect Files into Project Folder** includes
  sheet and logo files used by saved snapshots as well as the current version. Keep those files
  available, and keep the required fonts installed, to reproduce an older version.

- **Import history** — the Credits toolbar shows the last spreadsheet brought in and its local
  import time. **Import history…** there, or **File → Import History…**, lists sources newest first,
  including worksheet, outcome, and applied/skipped review decisions. Hover for the original
  path or Google Sheets link and import settings. History is saved in the project and retained
  through snapshot restores. Canceled imports are not recorded; repeated unchanged automatic
  checks do not add entries. Earlier import dates cannot be reconstructed for older projects.

- **When the client sends a revision** — **File → Update from Revised Sheet…** (Ctrl+U), or drop
  the new sheet on the window and choose *Update*. The project remembers the sheet as the client
  last sent it, so it can tell their changes from your edits:

  - Only the client's changes are listed — changed, added and removed rows, each with a tick box.
    Edits you made that they didn't touch (a typo fixed, a logo row added) are kept and not listed.
  - Select a change to compare **Current credits** with **Incoming spreadsheet**, with separate
    role/header/name cells, highlighted differences, and row numbers for each version. Previous
    and Next step through the review; the selected change says exactly what will happen.
  - Rows changed on both sides are marked *review your edit* and start unchecked. Check them
    to replace your edited rows with the incoming version; leave unchecked to keep yours.
    Separate inserted rows are aligned around existing rows, so adding list entries does not
    replace the whole list. Names within a single cell are not merged individually.
  - Finishing the review makes the incoming sheet the next comparison reference, including
    skipped changes. **Finish review — keep current credits** records an all-skipped review;
    **Cancel** changes neither the reference nor the import history.
  - Layout overrides, side-by-side arrangements, logos and their placement, dismissals, look and
    timing all carry over. With *Fit runtime* the spacing re-solves to the same runtime.
  - Afterwards the changed rows have a blue bar; the **changed rows** chip shows only those, and
    the tooltip says what each used to be. **··· → Clear change marks** when you've reviewed them.
  - **Copy change list** gives a plain-text list to confirm with the client. The whole update is
    one undo step, and a change you declined is not offered again by the next revision.

  *Reload Sheet (discard edits)* is the other thing: it throws the project's edits away.

- **Preview** — Space plays and pauses. With the preview focused, ← → step a frame (Shift for
  10) and ↑ ↓ jump between sections; the ticks on the timeline are the section headers, and
  clicking near one lands on it. **Guides** adds an action-safe box, the column centre line and
  panel cuts. "Updating…" in the corner means the picture is being re-laid-out.
- **Timing** — *Fit runtime*: give a runtime (`3:30`, `210s` or `5035f`) and frame rate; the tool
  picks an integer px/frame and scales the flexible spacing (leading, gaps) so the crawl lands on
  the frame exactly. *Manual speed*: set px/frame and spacing yourself; runtime is whatever results.
  Head/tail holds add black frames either side.
- **Look** — choose font family/style, font size and line spacing for section headings,
  credit roles, credit names, thanks/partner names and legal text. Heading gaps and name-column
  spacing sit beside their related text controls. **Ignore blank rows below section headings**
  is on by default: headings use **Space below heading** without extra blank-row gaps, while
  the source spreadsheet remains unchanged. Turn it off to retain blank-row spacing. **Show advanced settings** reveals letter
  spacing, uppercase/italic, widths, positioning, logo defaults and supersampling. Existing
  advanced values remain active while hidden. Each Look and Music control has a reset-arrow button
  to restore only that setting to its built-in default, scaled to the output resolution. Styles apply across the project; mark sections
  in Credits for their individual column layouts. Every change updates the preview.
- **Look → Music** — choose title, label and name fonts, sizes and line spacing, plus the
  gaps below titles, between songs and between labels/names. **Show advanced settings**
  reveals letter spacing, uppercase/italic and maximum line width. Explicit Music sections
  keep the spacing overrides chosen in their own Music… dialog.
  For selected words, edit the cell in Credits, select them and press Ctrl+I (stored as `*italic text*`).
  Italics use an installed italic face; a missing italic face produces an actionable preview error.
- **Click a credit in the preview** to pause and select its source cell in Credits, without
  changing the current preview position. Wrapped lines and side-by-side blocks retain their source links.
- **Layout checks** flag content beyond the left/right frame edges, content in the outer 5%
  side margins, possible text/logo overlaps, unreadable artwork, and logos enlarged beyond 150%
  of their source pixels. Overlaps use bounding boxes and are warnings for human review;
  intentional overlaps can be dismissed. Vertical frame entry/exit is normal for a scroll.
  These findings use the existing Errors navigation and dismissal controls.
- **Errors (inside Credits)** — affected cells are tinted red and outlined, including when selected.
  Click a marked cell to read its explanation, or use **Previous / Next** to step through findings
  and pause the preview at each credit. Errors and possible problems are labeled separately.
  Editing rechecks the sheet automatically; resolved highlights disappear.
- **Export** — **Resolution** (UHD 4K, DCI 4K, HD, DCI 2K, or a custom size) and **frame rate**;
  both also show in the header. Every size in the look is in pixels at the delivery size, so
  when the height changes you are asked whether to *scale the look* — fonts, spacing, logos,
  hand-placed offsets and a manual scroll speed all scale, giving the same picture and runtime at
  the new size — or change the *canvas only*, which keeps every size and re-centres the column.
  Changing the frame rate keeps the runtime and recounts the frames.
  Then folder, file name, codec (ProRes 422 HQ, ProRes 4444 with optional alpha, H.264 for
  review, or a PNG sequence) and the artwork for each logo slot. The header's **Export** button
  (Ctrl+R) renders with these settings and shows progress beside it. While it runs the button
  reads **Cancel export** (Ctrl+.): the encoder is stopped and the partial file removed. Optionally also write PNG
  panels + a Fusion comp.

Save the whole setup as a `.crawl.json` project (a dot in the title bar means unsaved changes;
recent files are under File → Open Recent), or just the look as a reusable house style.

**Moving or sharing a project.** Files inside the project's folder (the sheet, logo artwork, the
export folder) are saved as paths relative to the project file, so the folder can be moved,
zipped or opened on another Mac with nothing to fix. Files elsewhere are saved by full path;
**File → Collect Files into Project Folder** copies those into `<project>_assets` beside the
project and re-points it, making the folder self-contained. Fonts are not collected — they must
be installed on the other machine.

On opening, a file that has moved is looked for by name beside the project and re-linked. If the
sheet itself is gone the credits saved in the project are used; a logo that can't be found is
reported and flagged as an error on its row rather than silently drawn as an empty box.

**Command line**

```bash
.venv/bin/crawl lint   examples/sample_crawl.csv
.venv/bin/crawl fit    examples/sample_crawl.csv --runtime 3:30 --fps 23.976
.venv/bin/crawl render examples/sample_crawl.csv --runtime 3:30 --out render/ --look examples/sample.look.json
.venv/bin/crawl render examples/sample.crawl.json --codec prores4444 --alpha
.venv/bin/crawl render examples/sample.crawl.json --fusion
.venv/bin/crawl fonts  helvetica
```

`render` writes `<name>.mov` (or `.mp4` / a PNG folder) and `<name>_report.txt` with the speed,
spacing scale, frame counts and lint. With `--fusion` it also writes:

| File | What |
|---|---|
| `<name>_p01.png …` | content-only panels, no black padding, each under the 16,384 px GPU texture limit, cut only between groups |
| `<name>.comp` | full composition for Fusion Studio |
| `<name>.setting` | the node tree alone — paste into a Resolve Fusion page |

## How the movie is made

The whole crawl is drawn once as a single tall image with a frame of black above and below.
Frame *f* is a plain slice of that image, `speed` rows further down than frame *f − 1*, piped raw
into ffmpeg. Because the speed is a whole number of pixels there is no resampling anywhere: every
frame is pixel-identical to a crop of the master. A 3:30 crawl at 4K ProRes 422 HQ takes about five
minutes, all of it in the encoder. Output is tagged Rec.709, legal range.

## If the crawl seems to stutter

The file's motion is exact by construction, and you can measure it:

```bash
.venv/bin/crawl verify render/crawl.mov
```

(or **Export → Check a Rendered Movie…**). It decodes the movie and reports the real displacement
between every pair of frames and the spacing of their timestamps. `CLEAN` means every frame moves
the same whole number of pixels; a repeated or dropped frame shows up as a 0 px or double step.

A clean file can still look juddery on playback, for reasons outside the file:

- **Display refresh.** 23.976 fps doesn't divide into 60 Hz, so each frame is held for 2 then 3
  refreshes alternately. Scrolling text is the most sensitive thing there is to this. A display at
  24, 48 or 120 Hz shows each frame for the same time.
- **Player scaling.** A window that isn't at 100 % turns an 8 px step into a fractional number of
  screen pixels, which shimmers.
- **24 fps itself.** Sharp text moving several pixels per frame with no motion blur strobes a
  little even on a perfect display. Slower is smoother: fewer pixels per frame means a longer
  runtime or less content.

## How the Fusion comp works (optional)

One Loader per panel, merged over a black Background. Each Merge's Center is an expression
of `time`, not a keyframe:

```
Point(0.5, ((time - head) * speed - (panel_top + panel_height / 2)) / frame_height)
```

The top of the content starts just below the frame and moves `speed` whole pixels per frame;
panel tops and heights are kept even so the foreground always lands on whole pixels and never
resamples. No Text+ nodes, so Fusion stays fast.

For HDR/PQ deliveries render `luma16` and set the white level in the comp (e.g. ~203 nits)
rather than relying on 1.0.

## Sheet rules

The sheet follows the credits template:

- A workbook's `Crawl` tab is read if there is one; otherwise the import dialog asks which tab.
- Hidden Excel rows are excluded from credits. Empty row slots preserve source row numbers.
  Saved projects keep their imported snapshot; reopening the workbook refreshes source visibility.
- `(clear field)` markers are treated as empty cells, including in saved project edits.
- Col B = role/title · Col C = centered header (ALL CAPS) or song title · Col D = name(s).
- `\n` inside a Col D cell stacks names under one role.
- In the `MUSIC` section, quoted song titles are followed by role labels in B and names in C or D.
  Continuing names in C remain credit lines. Music labels and names are centered together.
- Blank rows separate groups; panel breaks only fall between groups.
- A run of six or more rows with only Col B filled is a single-column list (brand partners,
  special thanks) and is set in three balanced columns.
- `[Logo: …]` rows are logo slots; rows with `©` or long paragraphs are legal text.

## Layout

```
crawl/
  model.py    blocks: Header, RolePair, ListBlock, Logo, Legal → Group → Crawl
  ingest.py   sheet → model
  lint.py     findings for a human
  look.py     house style (JSON)
  fonts.py    installed-font scan, "Family:Style" → file
  text.py     metrics, tracking, wrapping
  timing.py   runtime ↔ integer speed ↔ spacing scale
  layout.py   baselines, column balancing, panel breaks
  render.py   draw a slice of the layout to an image
  export.py   tall master strip → ffmpeg → ProRes / H.264 / PNG sequence
  logos.py    ink-box trimming and balanced sizing for logo rows
  changes.py  three-way merge of a revised sheet into a built crawl
  verify.py   measure per-frame motion in a rendered movie
  fusion.py   optional .comp / .setting emitter
  project.py  Project (sheet + look + timing + output) and the prepare/render pipeline
  cli.py
  tools.py    where ffmpeg/ffprobe are (bundled, PATH, or imageio-ffmpeg)
  ui/         PySide6 app (theme.py holds the palette and stylesheet)
packaging/    PyInstaller spec, icon and ffmpeg fetcher; .github/workflows/build.yml builds releases
```

`examples/sample_crawl.csv` is a fictional sheet with the template's structure and its known
data problems, used by the tests. `examples/sample.look.json` and
`examples/sample.crawl.json` demonstrate a generic look and saved project.

```bash
.venv/bin/python -m pytest
```

## Not yet

- Live Google Sheets reads (export the `Crawl` tab for now).
- HDR/PQ output with a chosen title white level (render `luma16` panels with `--fusion` and grade for now).

EasyCrawl source is licensed under [Apache 2.0](LICENSE). Bundled third-party components retain their own licenses.


### Logos workspace

Open **Logos** to work on artwork separately from the scroll. Each section remains
linked to its original rows in Credits; **Show location in Credits** jumps back there.
Select a section and choose **Apply logo grid** to place one logo per cell, with 1–6
columns, adjustable spacing, and centered incomplete rows. This also converts an
existing same-range side-by-side arrangement without replacing the artwork.

Select artwork in the list or canvas. Drag to position it, use **Move earlier/later**
to change grid order, and adjust size, inversion, black/white points or automatic
black-point cleanup in the inspector. Choose original color or monochrome. The
canvas and the scroll use the same renderer; the main preview now preserves color.
Use **Add artwork** or **Replace selected artwork** for source files. Save Project
keeps grid, order and appearance settings; these changes participate in Undo/Redo.


In **Logos**, Shift/Cmd-click artwork on the canvas or use the list's extended
selection to select several logos. Drag any selected logo to move the group;
snapping uses the group's bounds. Option/Alt bypasses snapping. The alignment
menu aligns left/right/top/bottom edges or horizontal/vertical centers. Equal-gap
distribution needs at least three selected logos, keeps the outer two fixed, and
spaces the artwork edges evenly. Each operation is one undo step. The logo canvas
caches separate artwork layers while dragging and retains its selection and view
bounds across rebuilds.

## Building distribution installers

After the PyInstaller build, compile `packaging/windows-installer.iss` with Inno Setup,
passing `/DAppVersion=<version>`. The installer is written under `dist/installer/`.
The release workflow builds the Windows setup executable and the Mac drag-to-Applications
disk image automatically on version tags. Mac builds currently target Apple silicon.

Similar-name warnings compare spellings within each section, so names in different
departments or thanks sections do not trigger cross-section typo warnings. Blank rows
inside a headed section keep the same comparison scope.

Thanks columns fit the width of their names and are centered as a compact group.
Maximum section width controls wrapping; Space between columns controls the real gap
between the widest entries in adjacent columns.

Special thanks defaults to **Name order → Across rows — spreadsheet order**: the
first two names share a display row in a two-column layout. Choose **Down each
column** to fill the left column before the right. Entries and source rows stay intact.

In the Logos tab, **Replace selected logo**, **Add logo**, **Remove logo**,
**Logo library** and **Show locations** manage artwork and placeholders. Remove logo
removes selected slots from the current section, supports undo and keeps original
artwork files. Shared logos in other sections stay assigned.

The Credits toolbar contains **Rows**, **Layout** and the expand icon. Formatting,
bold, alignment and reset-to-section-style controls sit above it. Layout marks
section types and arranges sections in columns; artwork comes from **Logos → Logo
library**. **Rows → Review** holds preview-following, dismissed-warning and
change-mark controls. CSV export is under Export.

Drag entries up or down in the Logos list to reorder the credit grid, or use
the up/down order icons. Multiple selected logos move together in their
existing order. Reordering updates the list immediately, saves with the project
and supports undo; the first move creates a logo grid if needed. Canvas dragging
continues to adjust position rather than list order.

Hidden Excel / Google Sheets rows add neither credit text nor spacing. Visible blank
rows keep their normal group spacing. Original spreadsheet row numbers are retained
for preview selection, warnings and revision merges; hidden status saves with the
project and follows local row edits and undo. Older saved projects can recover hidden
status from a matching cached workbook without changing their credit text.

**Layout → Name column layout → Left, Center or Right** treats each populated
cell in the selected rows as a name. Use it for paired names in B/C or B/D, or a
standalone name. Both columns inherit the shared name font, size and line spacing;
each name aligns within its column, and multiline names wrap independently.
**Layout → Automatic** restores the usual role/name interpretation.

The **B** toolbar button adds a bold override to the
selected cells. The **Use section style** reset icon clears local text overrides. These choices save
with the project, support undo, and follow inserted rows and sheet updates. Bold
uses the font family's bold face and does not edit the Google Sheet or saved credit
text. The preview and exports include the override.

The **Text formatting…** toolbar button also overrides font, size,
font color, line spacing, left/center/right alignment, italic and uppercase for selected text
cells. Choose **Custom** to edit a value, or **On** or **Off** for a switch. Choose **Use section default** beside one setting to restore it, then click **OK**. When multiple cells have different values, **Keep mixed values** preserves them.
Size changes scale line spacing unless line spacing is overridden too. These local
settings do not change other headings or names. Use **Heading font and styling…**
in the Special thanks dialog to format just that section's heading.
The color picker includes a swatch, RGB controls and hex entry. Uncheck **Font color**
to inherit the section color again. Color applies to previews and color exports;
luminance-only panels remain monochrome mattes.

Spreadsheet row labels show the actual interpretation: Heading, Song title,
Role / name, Names only, Thanks, List, Music, Legal or Logos. A **✓** marks an
explicit layout choice; **\*** marks local text styling. Hover the row label for
details. **Layout → Show row types** toggles these labels without changing credits.
Mixed-case section headings use the same section-header style as uppercase
headings; song titles keep their separate music styling. **Layout → Section heading**
can explicitly mark a heading in any single populated cell.
Select a logo row and click **Edit logo block…** (or right-click and choose it) to
open the Logos page with that row's artwork selected. Existing grids retain their
**Edit logo grid…** label and also select the artwork on the chosen row.
Look font groups identify their normal position: centered section headings, role
text in the left column, names in the right column, thanks names in name columns,
and legal text in a centered block. Descriptions explain which text follows each
style and how local cell formatting takes precedence.

EPS artwork is accepted by **Add logo**, **Replace selected logo**, **Logo block**,
**My logos** imports and logo relinking. EasyCrawl converts EPS to a PNG up to
4096 pixels on its longest edge, preserves colors and unpainted transparent areas,
and keeps the original EPS in the local logo cache. Original artwork is unchanged.
The PNG is reused on later imports and is the asset saved with the project.
Initial EPS conversion needs [Ghostscript](https://ghostscript.com/releases/gsdnld.html)
installed separately. EasyCrawl detects standard Windows installations and common
Mac/Linux locations; `CRAWL_GHOSTSCRIPT` can point to a custom executable. The app
provides a setup link when the renderer is missing. Ghostscript is not bundled with
EasyCrawl. Converted PNGs need no extra helper to preview, export or use on another
computer after collecting the project's files.

**Format selected cells → Wrap text → On** wraps long text within its credit
column. To choose exactly where a line breaks, edit the cell and press **Alt+Enter**.
Headings, role titles and names reserve space for all their lines.

**Special thanks → Left name column alignment / Right name column alignment**
controls each outer names column independently. Choose **Right** on the left and
**Left** on the right to align both toward a centered gap. Centered middle-column
exceptions retain their position, and local cell alignment overrides still take
precedence over the section settings.

**File → Google Sheet is master for credit text** is enabled by default. Refresh
compares the full current project text against the Google Sheet, including previously
skipped differences, capitalization, insertions and deletions. All source changes
start selected for review; capitalization-only edits are labelled. Formatting and
artwork assignments remain in EasyCrawl for rows that still exist. Disable this
option to use the older three-way merge that preserves local text edits. Automatic
application still requires the separate **Apply Google Sheet Changes Automatically**
option.

Master-sheet refreshes preserve an assigned EasyCrawl logo row when it corresponds
to a source logo placeholder. Downloaded/private artwork, logo settings and grid order
remain in EasyCrawl. Center credit name formatting follows a standalone name moved
between source columns.

**Layout → Roles / names (two columns)** explicitly aligns roles rightward in
the left column and names leftward in the right column, using the normal credit
gutter and typography. It accepts populated role/name pairs and overrides automatic
or explicit compact music formatting for the selected rows.

**File → Open Project…** resumes a saved crawl. **Recent projects** lists saved
crawls with their layouts, artwork and timing. To start from a source, use **Import credit file…** or **Import Google Sheet…**. For later revisions, use **Update from
Revised Sheet…** or **Google Sheet → Refresh from Google Sheet**. Source imports do
not evict saved projects. **Import history…** beside the source name shows import
dates and review decisions.

For paired Special thanks lists, choose **Name order → Match spreadsheet columns**.
Left and right entries remain paired on their source rows, including missing cells;
long entries wrap within their own cell. A lone C-column entry is centered when B
and D are the name columns. New paired sections default to this mode. Existing
sections retain their saved mode until changed. Across rows and Down each column
remain available for rearranging a single-column source list.

The Credits toolbar and right-click menu share section markings. Right-click row
insertion/deletion is grouped under **Rows**. The automatic column-list layout is
**Layout → Name list in columns…**. Selected music and logo blocks expose their
own editor commands rather than the generic section-column dialog.

**Export → Export Credits as CSV…** is the single menu location for source-text
export. The main export command follows the selected codec or PNG sequence format,
and Cancel Export is available only while an export is running. Logo artwork is
managed in Logos and the preview inspectors, not in Export settings.

**Layout → Names only / alignment → Face center (like roles / names)** places
the left names at the normal role edge and the right names at the normal name
edge, keeping name typography on both sides. A single name stays centered. In
Special thanks settings, **Use role / name alignment** sets the same alignment
and center gap. Opening Special thanks from a heading or adjacent names-only
block recovers the complete section for editing.

Select empty rows and choose **Rows → Make empty rows visible as spacing** to
reserve one blank-row gap per selected empty row. Marked rows have a blue tint
and a **Spacing ✓** label; consecutive marked rows add separate gaps. This explicit
choice also overrides source-hidden status and the option to ignore blanks below
headings. **Clear explicit spacing** restores normal blank-row handling. The gap
height follows Look's blank-row spacing and runtime scaling. Text rows are never
hidden or emptied by this action. Marks save with the project, support undo and
follow row insertions, deletions and source updates.

### Compact workspace

**Review…** beside the Credits issue count opens a list filterable by severity
and issue type, with the section and exact spreadsheet cell for each entry.
Errors, warnings and informational notes are counted separately. Use **Show in
credits** to locate an issue or **Dismiss selected issue** after reviewing it.

Project files are explicitly read and written as UTF-8. Suspected garbled text
appears as a **Text encoding** warning, including text from imported sheets.
The review shows the current text and any reversible suggested correction;
**Apply suggested correction** changes only that cell and supports Undo. No
names are changed automatically. An unreadable replacement character needs a
manual check against the original source.

**Look**, **Timing**, and **Export settings** are in the top header; the left tabs
are Credits and Logos. The active header button is highlighted. **View → Jump to
section…** (Ctrl+J) opens the section finder. Headings and logos span the full
spreadsheet row visually, preserving their source cells. Subtle row colors help
identify block types; selection and warnings take priority.

On Logos, the collapsed block chooser shows **Block 1**, **Block 2**, etc. and the
total block count. Expand it for thumbnails and logo counts; hover for source
headings and rows. The viewer toolbar switches between **See in crawl** and
**Arrange logos**, and contains Layout, Align, Distribute, Set gap and Center pair.
Pair tools require exactly two selected logos. Distribute requires at least three
and retains the outer logos. Logo size, position and tone controls sit above the
viewer. Instructions are available in tooltips.

**File → Export → Review PDF…** saves a paginated visual proof of the whole crawl
or one section. The proof uses the current layout, fonts, colors and artwork.

**Import credit file…** and **Update from Revised Sheet…** accept Excel, CSV, TSV,
plain text, Apple Numbers, Word (.docx), and PDFs with selectable text. In Numbers,
choose the sheet/table containing the credits. Word reads body paragraphs and
tables in document order. Review the extracted columns for Word and PDF files;
PDF line breaks and multiple columns depend on the source layout. Scanned pages
need OCR first. A plain text file uses one row per line or tabs between cells.

Revision review identifies capitalization and possible spelling edits, credits
that moved, names reordered within a row, and removed section headings. The
side-by-side comparison shows the actual rows for each decision. An exact, unique credit moving between rows appears as one **Move credit** decision. Its checkbox controls both positions. Ambiguous matches and local conflicts retain their separate review decisions.
