# F2 item finder

Status: **Phases 3 (item memory) and 4 (search) done.**

## How to use it

- **`#finditem`**: type part of a name (case doesn't matter), or just press
  Return to list everything you remember seeing.
  - Results are grouped by level, with the same level names as Ctrl-O.
    Each level has up to two sections: **On the floor**, then **For sale**
    (shop goods whose price you were quoted). A container's contents are
    listed indented under it:

        The Dungeons of Doom: level 1
         On the floor
        a - an unlocked large box, last seen T:4
        b -   a clear potion, last seen T:4
        c - a ring mail, last seen T:13
         For sale
        d - 6 rocks, 42 zorkmids, last seen T:24

  - If a search matches only something inside a container, the container is
    still shown (without a letter) so you can see where it is.
  - Shop goods you only saw from a distance were never quoted a price, so
    they are listed under "On the floor".
  - Containers say "(contents unknown)" if you never looked inside, or
    "(empty)".
  - Corpses are never listed: they rot or get eaten, so an old sighting is
    useless. Other food is listed.
- **Pick a result** to see its level's remembered map, with the cursor on the
  item's square. `<` / `>` step to other levels, as in the level map viewer;
  Esc goes back to the game.
- **`m` then `#finditem`**: choose filters first:
  - item classes (`!` potions, `?` scrolls, …), only those you've seen;
  - `B`/`U`/`C`/`X`: blessed, uncursed, cursed, unknown, **as far as you
    know**;
  - `F`: for sale in a shop; `I`: inside a container.

  Choices in one group are alternatives ("potions or scrolls"); groups
  combine ("potions, inside a container").
- **Names use what you know now.** Once you identify clear potions as water,
  every remembered clear potion is listed as water.
- **What you remember can be out of date**: a monster may have taken
  something since. Hence "last seen".
- Searching takes no game time.

Wizard mode: `#wizitemmem` lists the raw memory (object ids, coordinates).

## What is stored

Each level's `struct mapseen` has a list of `struct itemmem` entries
(`include/dungeon.h`). Each entry holds:

- `obj`: a **full copy of the object as last seen**. Its pointers are cleared,
  and `where` is `OBJ_FREE`. Its known flags (`dknown`, `bknown`, `known`,
  `rknown`, `cknown`, `lknown`, `tknown`) are what the hero knew then.
  `ox,oy` is where it was. For contents, it's where the outermost container
  was.
- `oname`: the object's name (from `oextra`), if any.
- `cont_id`: 0 for the floor. Otherwise, the `o_id` of the container it was in.
- `seen`: the turn it was last seen.
- `price`, `price_contents`: the shop price quoted, and whether that price
  was for a container's contents.

Floor entries are keyed by (object, square); contents by (object, container).
Size: about 200 bytes per entry. Wizard `#stats` lists it as "seen items".

### Why a full copy

A hand-picked list of fields could miss one that `doname()` reads: candle
use, statue flags, novels, tin variety, and so on. A full copy is named
exactly like the real object was. Knowledge stays limited by the copied known
flags, just as for the real object.

**Rule for Phase 4:** never look at a copy's hidden fields directly. A BUC
filter must check `bknown`; matching by name must use `itemmem_name()`.

### Naming: `itemmem_name()`

- Builds a temporary object from the copy and formats it with
  `distant_name(tmp, doname)`, so names use **today's** discoveries.
- `xname()` calls `observe_object()`, which **sets `dknown`**, unless
  `gd.distantname` is set. Naming a snapshot directly would therefore reveal
  the appearance of something only ever seen from afar. `distant_name()` on
  an `OBJ_FREE` object always takes its "don't reveal" branch.
- `cknown` is cleared on the temporary object. The copy holds no contents,
  so `doname()` would otherwise say "empty". Phase 4 shows contents from the
  list instead.
- Clerics see BUC, as `xname()` does for them anyway. For a known artifact,
  `find_artifact()` runs again; that's harmless, because it already ran when
  the hero first saw it.

## When the memory changes

| Event | Hook | Effect |
|---|---|---|
| An object comes into view (top of a pile) | `map_object()` (`display.c`), if `cansee()` and not hallucinating | Adds or updates that object's floor entry. No price. |
| The hero is on a square and not blind | `itemmem_here()` after every hero action (`moveloop_core()`, after `vision_recalc()`) | The whole pile replaces the square's floor entries. In a shop, it includes the price `#look` quotes. |
| Blind `#look` / arriving on a pile | `look_here()` (`invent.c`) | Records exactly the objects it listed. |
| Looting a floor container (incl. `:` look inside) | `use_container()` at `containerdone:` (`pickup.c`) | If `cknown`, its contents replace the remembered contents. |
| Tipping a container | end of `tipcontainer()` | Its now-empty (or reduced) contents are recorded. The spilled objects are recorded by the per-action hook. |
| An object enters inventory | `addinv_core0()` (`invent.c`) | Forgets it and its contents (inventory isn't listed). |
| A container is seen without `cknown` | `itemmem_record()` | Its remembered contents are forgotten ("contents unknown"). |

None of these use game time or random numbers: `basic`, `levelmap` and `shop`
are unchanged. `get_cost_of_shop_item()` (used for prices) uses no RNG.

### Decisions (differences from the CLAUDE.md wording)

- **Standing = the whole pile**, also when `look_here()` only says "There are
  several objects here". `#look` would list them at no cost, so the hero
  effectively knows them. Blind, feeling costs a turn, so only what was
  actually felt is recorded.
- **Drops** are recorded: after dropping, the hero is standing on the pile.
  CLAUDE.md doesn't mention drops, but "where did I leave my stash?" is the
  main use.
- **Forcing a lock** doesn't reveal contents (CLAUDE.md lists forcing with
  looting). The contents are recorded when the box is then looted. If forcing
  destroys the chest, its spilled contents are recorded as floor objects.
- **The same object seen on two squares** (a pet carried it) gets two
  entries; the old one is stale until the hero stands there again. Picking
  it up forgets both.
- **Remote object detection** (potion, spell, crystal ball) calls
  `map_object()` for objects the hero can't see. The `cansee()` guard keeps
  them out.
- **"Last seen"** is the turn of the action that showed the object. For
  objects in view it updates whenever the display touches the square
  (moving, a redraw, a restore), not every turn.
- **Levels without `hero_memory`** record nothing.

### Co-op later

All of it is in `mapseen.itemmem`. A second hero needs its own list per level
(or its own `mapseen` chain), and the hooks need to know which hero saw what
(e.g. `map_object()` would ask which hero `cansee()`).

### Save file

`save_mapseen()`/`load_mapseen()` write a count, then for each entry:
`Sfo_obj`, the name, `cont_id`, `seen`, `price` and `price_contents`.
**`EDITLEVEL` 1 → 2.** `dungeon.c` compiles cleanly with `-DSFCTOOL`.

## The search (`#finditem`)

`dofinditem()` and its helpers are in `src/dungeon.c`, after the recording
code:

- `finditem_match()`:
  - Corpses (`otyp == CORPSE`) never match. They stay in the item memory
    (`#wizitemmem` shows them, and they still keep a container from counting
    as "(empty)"); only the search leaves them out. `finditem_filters()` skips
    them too, so `%` isn't offered when the only food seen was corpses.
  - The class filter uses `oclass`. That's always visible: the map glyph
    shows the class.
  - The BUC filter uses only what the hero knows: `bknown`, then
    `blessed`/`cursed`. Anything without `bknown` counts as "unknown" (`X`).
  - The text must be a case-insensitive substring (`strstri()`) of
    `itemmem_name()`, the name as shown.
- Layout (`dofinditem()`): for each level, two passes over the top-level
  entries (floor items, and contents whose container isn't remembered):
  first those without a price ("On the floor"), then those with one ("For
  sale"). `finditem_add()` adds an entry and then, recursively and indented
  two spaces per level, the entries whose container it is
  (`finditem_container()`: same `o_id` and square).
- `finditem_shown()`: an entry is shown if it matches, or if something
  inside it does. A container shown only for its contents gets no menu
  identifier (unselectable) and four extra spaces, to line up past "a - ".
- `finditem_describe()` builds the result line:
  - the name;
  - "(contents unknown)" if `!cknown`, or "(empty)" if no remembered contents;
  - ", in a container" only for contents whose container isn't remembered;
  - the price: ", N zorkmids" in the "For sale" section, ", for sale, N
    zorkmids" elsewhere (a priced item inside an unpriced container), or
    ", contents, N zorkmids";
  - ", last seen T:n".
- `finditem_level_ok()` searches the same levels as the level map viewer: not
  unreachable, not forgotten, not the main dungeon while in the endgame.
- `finditem_filters()` (`m` prefix): a pick-any menu. Classes are listed only
  if some remembered object has them, each on its class symbol; then
  `B`/`U`/`C`/`X`, `F` and `I`.
- Picking a result calls `view_levelmap(mptr, x, y)`. On that level, the
  cursor is put on `<x,y>` after the header, and the header says "[item at
  cursor; <>, ESC]".
- The command is `GENERALCMD | CMD_M_PREFIX` and returns `ECMD_OK` (no time).
  Naming goes through `distant_name()`; nothing touches the core RNG.

### Checked

- `finditem` scenario (wizard mode, 40 assertions, see Tests).
- By hand in normal mode (2026-11-23): replay `basic` to Dlvl 2. Then
  `#finditem`, pick a result, `<`, Esc, `m #finditem` with a filter, a
  search, and six `s` plus `^R`. The screen is identical, `T:` and monsters
  included, to six `s` plus `^R` alone. The results there show "a potion of
  paralysis" for a potion seen on the floor, identified later by drinking
  one.
- Not checked: the curses interface (the harness drives tty only).

## `#wizloaddes` fix (found here)

`#wizloaddes` discarded the level's `mapseen` (via `lspo_reset_level()` →
`makemap_prepost()`) and never made a new one, so a Lua-built test level had
no item memory, no level map and no overview. `wiz_load_splua()` now calls
`init_mapseen()`, as `mklev()` does (wizard mode only).

## Tests

`test/golden/scenarios/itemmem.keys` (wizard mode), on
`test/golden/lua/golden_items.lua`. `#wizitemmem` lists the memory, and
`!screen-has` / `!screen-lacks` check it:

1. From a distance: containers "contents unknown", only the pile's top
   (ring mail). No apples, lock pick, box contents, gems, wand or shop goods.
2. Standing on the pile: all three objects.
3. Picking up the apples forgets them; dropping them one step away records
   them there.
4. Looking inside the large box records its contents, with unidentified
   names. Taking the potion out forgets it. Tipping moves the scroll to the
   floor.
5. A failed `#loot` on the locked chest: still "contents unknown", no rubies.
6. The dark room: the wand isn't recorded from two squares away, only from
   next to it, and only as "a wand".
7. The shop seen through its door: goods without a price. Standing on goods:
   "6 rocks (for sale, 42 zm)".
8. On another level, the whole listing survives save/restore unchanged.
9. Object detection on Dlvl 3: still 14 items.

Mutation check: without the `cansee()` guard in `map_object()`, step 9 fails.

`test/golden/scenarios/finditem.keys` (wizard mode), same level:

1. Look into the box. `#finditem potion` → "a clear potion, in an unlocked
   large box, last seen T:…". Picking it shows the map with "item at cursor"
   (the transcript records the cursor on the box's square).
2. `elbib` finds "a scroll labeled ELBIB YLOH" (case ignored). `wand` (never
   seen) finds nothing.
3. Filters: `B` finds nothing (the potion is blessed, but the hero doesn't
   know). `X!` → only the potion. `?` → only the scroll. `I` → both, no ring
   mail.
4. Wish for and read a scroll of light: `light` now finds "a scroll of light,
   in an unlocked large box", and "ELBIB" is gone.
5. In the shop: `F` → "6 rocks, on the floor, for sale, 42 zorkmids". No box.
6. From Dlvl 3: results under "level 1" and "level 3 <- You are here."
   Picking a Dlvl 1 item shows Dlvl 1's map, marked. Still T:24 (no time).
7. Save/restore: the same results screen.

Writing test levels, gotchas:

- `des.map` rows must all be as wide as the first, or later rows run
  together.
- `des.stair("up", …)` was ignored on this level; the up stairs landed in the
  shop at random.
- Object ids (`#n` in the listing) change when the level changes, so don't
  assert on them.
