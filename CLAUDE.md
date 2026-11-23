# NetHack 5.0 quality-of-life features: guide for Claude Code

> **Status: v1.0.** Two single-player features for vanilla NetHack 5.0, agreed with
> Laura. **No co-op or multiplayer code belongs on this branch.** That work happens
> separately, and will later be built on top of this branch.

## Goal

Add two "memory aid" features to NetHack 5.0 without changing how the game plays:

- **F1. Level map viewer:** look at the remembered map of any level you've visited.
- **F2. Item finder:** search every item you've seen on visited levels, including
  inside containers and in shops.

Both show **only what the hero has seen and knows**. They are a convenience, never a
spoiler.

## Ground rules

1. **Never change gameplay.** A game must *play* exactly like vanilla 5.0: the same
   RNG calls in the same order, so a seeded game replays identically. The new commands
   use **no game turns and no random numbers**. The golden-master test (Phase 0b) must
   pass on every change.
2. **Never reveal what the hero doesn't know.** If in doubt, show less.
3. **Small steps.** One concern per commit. Build and run the tests before every
   commit. Never mix a refactor and a behaviour change in one commit.
4. **Match NetHack's style.** Follow the surrounding C99 style (4-space indent, K&R
   braces, `staticfn`, existing naming). Never reformat code you aren't changing.
5. **Write down what you learn.** Put findings in `doc/features/`. Future sessions
   read these instead of rediscovering them.
6. **Ask before** save-format changes beyond those described here, or anything marked
   **[OPEN]**.
7. **Keep a future second hero in mind.** A co-op branch will later give each hero
   their own map and item memory. Keep the new memory in a self-contained structure
   that could become per-hero, rather than spreading it across unrelated globals.
   Don't build anything co-op-specific now.

## Facts about the 5.0 codebase (verified from the source)

| What | Where |
|---|---|
| Base | tag `NetHack-5.0.0_Released` |
| Overview (Ctrl-O) | `dooverview()` in `src/dungeon.c` |
| Per-level overview data | `struct mapseen` in `include/dungeon.h`: one per visited level, already saved and restored with the game; holds features, annotations (`custom`) and room info |
| `#terrain` | `doterrain()` in `src/cmd.c`, drawing via `reveal_terrain()` in `src/detect.c` |
| Hero's map memory | `struct rm` in `include/rm.h`: `glyph` ("what the hero thinks is there"), `seenv`, `waslit` |
| Item names | `doname()`, `doname_with_price()`, `xname()` in `src/objnam.c` |
| Looking at a pile | `look_here()` / `dolook()` in `src/invent.c` |
| Opening containers | `doloot()` and `use_container()` in `src/pickup.c` |
| Shop prices | `price_quote()`, `get_cost()` in `src/shk.c` |
| Level save/load | `savelev()` / `getlev()`. Only the current level is in memory |
| RNG | `src/rnd.c` (`set_random()`) |
| Existing tests | `test/*.lua`, run in wizard mode with `#wizloadlua` (see `test/README.md`) |
| macOS build | `sys/unix/hints/macOS.500`; `make fetch-lua` downloads Lua |

## F1. Level map viewer

Look at the map of any visited level, as the hero remembered it.

- **Shows the hero's memory, not the truth.** Each square appears as the hero last
  remembered it (the remembered glyphs, as `#terrain` draws them), exactly as it was
  when they left. Unexplored areas stay blank, items appear where they were last seen,
  and no monsters are shown apart from remembered `I` markers.
- **Browsing:** in the Ctrl-O (`#overview`) list, pick a level to view its map
  full-screen. `<` and `>` step up and down through visited levels (across branches,
  in overview order), and Esc returns to the game. Show the level's overview line and
  any `#annotate` note above the map. Also add a direct command (name TBD, e.g.
  `#levelmap`).
- **Free action:** no game time, no RNG calls.
- **Storage:** when the hero leaves a level, copy its remembered map (per square: the
  remembered glyph, plus whatever the drawing needs, such as `seenv` and `waslit`) into
  a per-level snapshot. Attaching it to that level's `struct mapseen` is the natural
  home, since mapseen is already saved and restored. Show the *current* level from live
  memory. **Don't** read other levels back out of the level files: `getlev()` makes a
  level current and has side effects. Size is about 7 KB per level.
- [OPEN] Whether the snapshot should be updated by things that change the hero's
  memory remotely, such as magic mapping or clairvoyance on another level. Default:
  no, snapshot only on leaving.

## F2. Item finder

Search every item the hero has seen on visited levels, including inside containers and
in shops.

- **Its own item memory.** NetHack's map memory only keeps the top item of each pile
  and knows nothing about container contents, so F2 keeps a separate list. Each entry
  holds:
  - a snapshot of the object: type, quantity, corpse type, name, BUC, enchantment,
    erosion, and the per-object "known" flags `dknown`, `bknown`, `known`, `rknown`
    *as the hero knew them*;
  - level, x/y, and where it is (floor, or inside which container);
  - the turn it was last seen;
  - for shop goods, the price quoted.
- **When entries are added or updated:**
  - Seeing a square from a distance adds or updates only its **top** item.
  - Standing on a square, or looking at it with `:`, shows the **whole pile**, so all
    of that square's floor entries are replaced.
  - Opening a container (`#loot`, `#tip`, or forcing it open) replaces that
    container's contents. Unopened or locked containers list as "contents unknown".
  - Picking an item up removes it from the list.
  - Items in the hero's own inventory aren't listed.
- **Names use today's knowledge.** Build a temporary object from the snapshot and
  format it with the normal naming code (`doname()`), so names reflect current
  discoveries. Once "clear potion" is identified as water, every entry says water.
  The snapshot's per-object known flags must be the ones the hero had when they saw it,
  so nothing leaks.
- **Shops included.** Record goods with the quoted price ("for sale, 266 zm"). These
  change most often, so the last-seen turn matters most here.
- **Stale by design.** Entries reflect the last sighting. A monster may have taken the
  item since. Show "last seen T:12345" on every result.
- **Search UI:** a new command (name TBD, e.g. `#finditem`) asks for text and matches
  case-insensitively on the displayed name, with optional filters by item class
  (`!`, `?`, `=`, …), BUC, "for sale" and "in containers". Results are grouped by
  level, showing location and last-seen turn. **Selecting a result opens the F1 map of
  that level with the square highlighted.**
- **Free action:** no game time, no RNG calls.
- **Storage:** saved in the save file. Small: a few hundred bytes per entry.

## Phased plan

Each phase ends with something that runs. Don't start a phase until the previous
one's tests pass.

| Phase | Deliverable | Done when |
|---|---|---|
| **0. Setup** | Vanilla 5.0 builds and runs on macOS | `nethack` starts; Laura can play a turn |
| **0b. Golden master** | Scripted, seeded run that records a dump/transcript; comparison script | Running twice gives identical output; one command runs it |
| **1. F1 storage** | Per-level map snapshot taken on leaving a level; saved and restored | A Lua or scripted test: visit a level, leave, save, restore, snapshot matches what was remembered |
| **2. F1 viewer** | Viewing from Ctrl-O, `<`/`>` browsing, direct command | Laura can browse all visited levels; golden master unchanged |
| **3. F2 memory** | Item memory recording, following the rules above | Tests cover distance vs. standing, `:`, containers, pickup, shops; nothing unseen recorded |
| **4. F2 search** | Search command, filters, results list, jump to F1 map | Searching finds items with correct current names; golden master unchanged; survives save/restore |

## Testing

Laura works in test automation, so tests come first.

- **Golden master:** a fixed RNG seed plus a fixed keystroke script, driven through a
  pseudo-terminal (for example Python `pexpect`), saving the final dumplog or screen.
  Any unintended gameplay change shows up as a diff. The scripts must not use the new
  commands, so the output stays comparable with vanilla.
- **Lua tests:** extend `test/` where wizard-mode Lua can set up situations (placing
  objects, containers, shops).
- **Leak tests:** for F1 and F2, check that unseen squares, unopened containers and
  unidentified properties never appear.

[OPEN] How to fix the RNG seed for tests: check whether 5.0 exposes a way. Otherwise
add a debug-only option that calls `set_random()` with a fixed value.

## Licence

NetHack is under the NetHack General Public License. Keep the licence and copyright
headers intact.
