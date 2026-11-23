# F1 level map viewer

Status: **Phases 1 (storage) and 2 (viewer) done.**

## How to use it

- **Ctrl-O** (`#overview`) lists the interesting levels you have visited, each
  with a letter. Pick one to see its map full-screen.
- **`#levelmap`** shows the same list with *every* visited level. Pick one.
- In the viewer:
  - **`>`** goes to the next level down, **`<`** to the next level up. Levels
    are in overview order: by dungeon, then depth. Going down past the last
    level of the Dungeons of Doom continues into the next branch (e.g. the
    Gnomish Mines).
  - **Esc** (or `q`) goes back to the game.
- The line above the map names the level, with the same text as Ctrl-O:
  features ("A fountain."), your `#annotate` note in quotes, and
  "<- You are here." for the current level.
- **`m` Ctrl-O** still annotates: pick a level and type a note. The note then
  shows in Ctrl-O and above that level's map.
- The map is your hero's memory: the current level as you remember it right
  now, any other level as it was when you last left it. No monsters, except
  remembered `I` markers, and nothing you never saw.
- Viewing takes no game time.

## What is stored

When the hero leaves a level, the game copies the remembered glyph of every
square, `levl[x][y].glyph`, into a `struct levelmap` attached to that level's
`struct mapseen` (`include/dungeon.h`):

    struct levelmap {
        int glyph[COLNO][ROWNO]; /* what the hero thought was there */
    };

- `mapseen.levelmap` is null until the hero first leaves the level. It is
  overwritten each time they leave again.
- The current level is never read from its snapshot. It is shown from live
  memory (`levl[][].glyph`), so it is always up to date.
- 80 × 21 × 4 bytes = 6,720 bytes per visited level. Wizard-mode `#stats`
  lists it as "level maps".

### Why only the glyph

CLAUDE.md suggested `seenv` and `waslit` "or whatever the drawing needs". The
drawing only needs the glyph. The remembered glyph already holds everything the
viewer shows:

- lit vs. dark floor (distinct glyphs in 5.0)
- remembered objects (top of pile), traps and `I` markers
- "never seen" (`GLYPH_UNEXPLORED`)

It never contains monsters. `seenv`/`waslit`/`lastseentyp` would only matter
for redrawing terrain from scratch (`#terrain`'s "without objects" modes). If a
later phase wants such filters, add `lastseentyp` then, with another
`EDITLEVEL` bump.

### When it is taken

`goto_level()` (`src/do.c`) calls `levelmap_snapshot()` (`src/dungeon.c`)
right after `recalc_mapseen()`, before the old level is saved. Every way of
leaving a level goes through here: stairs, trapdoors and holes, level
teleport, falling, and migration.

- Levels without `hero_memory` (the level flag that turns off map memory) get
  no snapshot, and any older one is dropped. If in doubt, show less.
- 5.0's amnesia no longer forgets maps, and nothing sets
  `mapseen.flags.forgot`. So there is no "forget other levels" case to handle.
  If one is ever added, it must free `mapseen.levelmap` too.
- **[OPEN] in CLAUDE.md, default kept:** magic mapping or clairvoyance never
  updates another level's snapshot. Snapshots change only on leaving.
- No game time and no RNG: it's a plain copy loop.

### Save file

`save_mapseen()`/`load_mapseen()` write a boolean "has a map" and then
`COLNO × ROWNO` ints, using the plain `Sfo_int`/`Sfi_int` savers. That avoids
the ctags-generated struct savers (`util/sftags.c`). **`EDITLEVEL` went from 0
to 1** (`include/patchlevel.h`), so saves and bones from before this change are
rejected instead of misread. `load_mapseen()` is also compiled into `sfctool`;
`dungeon.c` builds cleanly with `-DSFCTOOL`. Building `sfctool` itself needs
Universal Ctags, which macOS doesn't ship, so it fails on vanilla too.

The snapshot is freed in `rm_mapseen()` (wizard `#wizmakemap`) and when the
dungeon data is freed (`save_dungeon(…, free_data)`).

### Co-op later

Everything a hero remembers about other levels' maps is in
`mapseen.levelmap`. A second hero would need either a `levelmap` per hero in
`mapseen` or a per-hero `mapseen` chain. No other global holds this data.

## The viewer

- `view_levelmap(mapseen *)` in `src/detect.c`, next to `reveal_terrain()`,
  draws the snapshot (or the live memory for the current level) with
  `show_glyph()`. It then reads keys with `readchar()` until Esc or `q`, and
  redraws the real map with `map_redisplay()`.
- It deliberately does **not** use `browse_map()`/`getpos()` autodescribe.
  That describes the *current* level's actual contents, which would be wrong
  for another level and could leak information.
- The header is one message line, cut to fit (with a `[<>, ESC]` hint when
  there's room). A longer line would trigger a tty `--More--`, which would
  swallow the next key. It is not added to message history (`^P`).
- Helpers in `src/dungeon.c`:
  - `levelmap_viewable()` skips levels that `#overview` hides (unreachable,
    forgotten, the main dungeon once in the endgame) and levels with no stored
    map.
  - `levelmap_step()` finds the next or previous viewable level in the
    `mapseen` chain (overview order).
  - `levelmap_header()` reuses `overview_levelline()` and
    `overview_interests()`, which a no-change refactor split out of
    `print_mapseen()`.
- Entry points:
  - `show_overview()`'s `why` 0 (Ctrl-O) and the new `why` -2 (`#levelmap`)
    are pick-one menus that open the viewer.
  - `why` -1 (`m` Ctrl-O) still annotates.
  - The end-of-game overview (`why` 1, 2) is unchanged.
  - `print_mapseen()` gives every level line a menu identifier while
    playing, and indents with `TAB` only at the end of the game, so letters
    line up.
- **Only Ctrl-O's look changed** (agreed with Laura): level lines now carry
  menu letters. `basic`'s re-recorded baseline differs from the vanilla one in
  exactly those two lines.

### No game time, no random numbers

- `#levelmap` and Ctrl-O return `ECMD_OK`, which takes no time. Drawing uses
  `show_glyph()`, `docrt()` and `map_redisplay()`. These touch only the
  display RNG, which only hallucination uses, never the core RNG.
- Checked by hand in normal mode (2026-11-23): replay `basic` to Dlvl 2, then
  `#levelmap`, view Dlvl 1, `>`, `<`, Esc, then search 6 times and press `^R`.
  The whole screen, including monster positions and `T:`, is identical to
  searching 6 times without viewing.
- Gotcha: right after an action, the tty status line can show a stale `T:`
  until something redraws it. Compare turn counts after `^R`.
- Not checked: the curses interface. The harness drives tty only.

## Test

`test/golden/scenarios/levelmap.keys` (wizard mode):

1. Records Dlvl 1 with `#terrain` "known map without monsters" (the hero's
   memory) and level-teleports to Dlvl 2.
2. Checks with `!same-map` that `#levelmap` shows the same map rows for Dlvl 1.
3. Records Dlvl 2, saves and restores, and checks Dlvl 1 again.
4. In the viewer, steps `>` to Dlvl 2, `<` back, then `>` twice (staying put at
   the deepest level).
5. Goes back to Dlvl 1 and checks Dlvl 2's snapshot.
6. Checks that the live view of the current level equals `#terrain`.
7. Picks a level from Ctrl-O.
8. Annotates Dlvl 1 with `m` Ctrl-O and checks the note in the viewer's header.

- No snapshot shows a monster (the kitten and an orc were in view) or a square
  the hero never saw.
- The turn counter stays at T:1 throughout, so no game time is used.
- Mutation: saving "no map" instead of the map makes `levelmap` FAIL after the
  restore. Reverted, it passes.
- `basic` (which goes down and back up) and `shop` are unchanged, so taking
  snapshots doesn't affect gameplay.
