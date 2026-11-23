# F2 item finder

Status: **Phase 3 (item memory) done.** The search command (Phase 4) isn't
built yet. Until then, wizard-mode `#wizitemmem` lists what is remembered.

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

Writing test levels, gotchas:

- `des.map` rows must all be as wide as the first, or later rows run
  together.
- `des.stair("up", …)` was ignored on this level; the up stairs landed in the
  shop at random.
- Object ids (`#n` in the listing) change when the level changes, so don't
  assert on them.
