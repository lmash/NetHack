# F1 level map viewer

Status: **Phase 1 (storage) done.** The viewer itself (Phase 2) is not built
yet. Until then, wizard-mode `#wizlevelmap` shows what is stored.

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

## Drawing (so far)

`show_levelmap(mapseen *)` in `src/detect.c`, next to `reveal_terrain()`, draws
either the snapshot or the live memory with `show_glyph()` on the map window.
It waits for a key, then redraws the real map with `map_redisplay()`. It
deliberately does **not** use `browse_map()`/`getpos()` autodescribe: that
describes the *current* level's actual contents, which would be wrong for
another level and could leak information. Phase 2 needs its own cursor
descriptions, if any.

`#wizlevelmap` (wizard mode only, `src/wizcmds.c`) lists the levels you can
show (any with a snapshot, plus the current one) and calls `show_levelmap()`.

## Test

`test/golden/scenarios/levelmap.keys` (wizard mode). It records Dlvl 1 with
`#terrain` "known map without monsters" (the hero's memory), level-teleports to
Dlvl 2, and checks with `!same-map` that `#wizlevelmap` shows the same map rows.
Then it records Dlvl 2, saves and restores, checks Dlvl 1 again, goes back to
Dlvl 1, and checks Dlvl 2's snapshot. Finally it checks that the live view of
the current level equals `#terrain`.

- No snapshot shows a monster (the kitten and an orc were in view) or a square
  the hero never saw.
- The turn counter stays at T:1 throughout, so no game time is used.
- Mutation: saving "no map" instead of the map makes `levelmap` FAIL after the
  restore. Reverted, it passes.
- `basic` (which goes down and back up) and `shop` are unchanged, so taking
  snapshots doesn't affect gameplay.
