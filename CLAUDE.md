# NetHack Co-op: guide for Claude Code

> **Status: v0.2.** Written with Laura before any code exists. All design decisions
> are made (see Decisions). Anything still marked **[OPEN]** is a technical question
> to investigate. Don't build anything that depends on an [OPEN] item without asking
> first.

## Goal

Two players (Laura and her brother) play **one shared game of NetHack 5.0**, each
controlling **their own full hero**: own role, inventory, HP, luck, prayer timeout and
intrinsics, in the same dungeon, against the same monsters.

This is a fork of vanilla NetHack 5.0.0, not a new game. It should feel like NetHack,
with a second `@` beside you.

### Non-goals (for now)

- More than 2 players (keep the design N-friendly where it's cheap, but only test 2).
- Public servers, matchmaking, accounts.
- Changing game balance, apart from rules that co-op strictly needs.
- Windows, Qt or X11 interfaces. Target **tty** (and **curses** if it comes cheaply).

## Ground rules

1. **Never break single-player.** A one-hero game must behave *exactly* like vanilla
   5.0. That means the same RNG calls in the same order, so a seeded game replays
   identically. The golden-master tests (see Testing) must pass on every change.
2. **Feature flag.** All co-op code sits behind the compile-time flag `MULTIPLAYER`,
   *and* a runtime check that more than one hero is active. With the flag off, the
   build should be byte-for-byte vanilla behaviour.
3. **Small steps.** One concern per commit. Build and run the tests before every commit.
   Never mix a refactor and a behaviour change in one commit.
4. **Match NetHack's style.** Follow the surrounding C99 style (4-space indent, K&R
   braces, `staticfn`, existing naming). Never reformat code you aren't changing.
5. **Write down what you learn.** Put findings in `doc/coop/` (for example
   `hero-globals.md`). Future sessions read these instead of rediscovering them.
6. **Ask before** large renames touching more than ~10 files, save-format changes,
   or anything marked [OPEN].

## Facts about the 5.0 codebase (verified from the source)

| What | Where |
|---|---|
| Base | tag `NetHack-5.0.0_Released`, branch `NetHack-5.0` |
| Main game loop | `src/allmain.c`: `moveloop()` calls `moveloop_core()` once per player action |
| The hero | global `struct you u` (`include/you.h`, defined in `src/decl.c`) |
| Worn and wielded items | globals `uwep`, `uarm`, `uswapwep`, etc. in `src/decl.c` |
| Inventory | `gi.invent`. Most globals live in "instance globals" structs named `ga`…`gz` by first letter (`include/decl.h`) |
| Scale of hero coupling | `u.ux` alone appears ~1,350 times across ~83 files; `gi.invent` ~315 times |
| RNG | `src/rnd.c` (`set_random()`, ISAAC64) |
| Interfaces | `win/tty`, `win/curses`, `win/shim` |
| Existing tests | `test/*.lua`, run in wizard mode with the `#wizloadlua` command (see `test/README.md`) |
| macOS build | `sys/unix/hints/macOS.500`; `make fetch-lua` downloads Lua |

Only the **current level** is kept in memory. Other levels are saved to files
(`savelev()`/`getlev()`). This drives the "party" rule below.

## Core design

### 1. Hero context switching (the key idea)

Rather than rewriting thousands of `u.` references, keep **one active hero** in the
existing globals and **swap hero state in and out** when control changes:

- `struct hero_state` holds everything per-hero: `u`, `gi.invent`, the equipment
  pointers (`uwep`, `uarm`, …), and any other per-hero globals found in the audit.
- `heroes[MAX_HEROES]` stores the inactive copies. `hero_activate(i)` saves the
  current globals into `heroes[cur]` and loads `heroes[i]`.
- Most existing code ("you hit the newt") keeps working unchanged for whichever hero is
  active.
- Only places that must consider **both** heroes need new code: drawing the other `@`,
  monsters choosing a target, collisions, vision, and level changes.

The risk is that a per-hero global gets missed, so state leaks between heroes. The
audit (Phase 1) and the swap round-trip test exist to catch exactly this.

### 2. Turn order

Each hero keeps their own movement points and speed (`u.umovement`). In
`moveloop_core()`, every hero with enough movement acts, in order, before monsters
move. A fast hero still gets extra actions. Prompts and the status line always show
whose turn it is.

### 3. Monsters

When a monster acts, it picks a target hero (nearest visible, or whoever attacked it
last). That hero is activated for the duration of the monster's attack, so existing
attack code ("the jackal bites!") applies to the right person. Messages name the target.

### 4. The party rule (levels)

Both heroes are **always on the same level**.

- Stairs, ladders and portals only work when the other hero is adjacent. Both move
  together, like a leashed pet.
- Involuntary level changes (trap doors, holes, level teleport, falling in Sokoban)
  **pull the other hero along**, with a message.

This avoids keeping two levels live at once. Splitting the party is a possible
far-future feature.

### 5. Display and vision

**Target: separate screens.** Each player sees only their own hero's view on their own
terminal: their own map, inventory, menus and prompts. **Hotseat** (one shared screen)
is a temporary stepping stone so phases 3–8 can be built and tested without networking.
Everything built in hotseat must not block the split.

- **Per-hero vision and map memory from the start.** Each hero has their own field of
  view and their own memory of the map. Today `struct rm.glyph` in `include/rm.h`
  stores "what the hero thinks is there", one per square, so it must become per-hero.
- **Hotseat display:** show the *active* hero's view (not a union), so the split later
  is just "send each view to a different screen".
- The other hero is drawn as `@` in a distinct colour when seen.
- Messages describe events from each viewer's perspective ("You hit the newt" for
  one player, "Laura hits the newt" for the other).

### 6. Separate screens: architecture (Phase 9)

One **game server process** owns the game state. Each player runs a **thin client**
that draws with curses and sends keystrokes.

- NetHack routes all drawing and input through a table of interface functions
  (`windowprocs`, `include/winprocs.h`). Build a **network interface port** that
  forwards those calls to the right player's client over a socket. Map updates go to
  everyone who can see them; menus, prompts and inventory go only to their owner.
- Starting points: `win/shim/winshim.c` already turns every interface call into a
  callback (built for libnethack/WebAssembly), and `win/chain/` can sit between the game
  and an interface (`wc_trace.c` logs every call, which is also useful for tests).
- Input: the server only reads keys from the client whose hero is active, and shows
  "waiting for <name>…" to the other player.
- Transport: plain TCP on a home network or over Tailscale to start. If it moves to a
  rented server later (decision 3), nothing in the protocol should assume both players
  are on Laura's machine.

## Phased plan

Each phase ends with something that runs. Don't start a phase until the previous
one's tests pass.

| Phase | Deliverable | Done when |
|---|---|---|
| **0. Setup** | Fork; vanilla 5.0 builds and runs on macOS | `nethack` starts; Laura can play a turn |
| **0b. Golden master** | Scripted, seeded single-player run that records a dump/transcript; comparison script | Running twice gives identical output; it runs in CI or with one command |
| **1. Audit** | `doc/coop/hero-globals.md` listing every per-hero global, with file counts and notes | Reviewed by Laura |
| **2. Hero state** | `struct hero_state` with save/swap; single hero only | Golden master unchanged; a test swaps a hero out and back with no state change |
| **3. Second hero exists** | P2 created at start (own role/race, P1's alignment, decision 6), placed next to P1, drawn on map | Both `@` visible; P2 can't act yet |
| **4. Hotseat turns** | Turn loop alternates heroes; input goes to the active hero | Both can walk, fight, pick up and use items |
| **5. Monsters and combat** | Target selection; attacks hit the right hero | Monster attacks and kill credit land on the right hero |
| **5b. Pets** | Owner field on tame monsters; each hero's starting pet; pet movement and following use the owner, not the active hero (decision 8) | Each pet follows its own hero; taming credits the hero who tamed it |
| **6. Party rule** | Stairs need adjacency; trap doors drag both | Both can descend; falling pulls both |
| **7. Death** | Dead hero leaves a corpse and their player becomes a spectator; game ends when both are dead (decision 4) | One hero dies and the other plays on to their own death; the end-of-game screen lists both |
| **8. Save/restore** | Save file holds both heroes; bones disabled with 2 heroes | Save, quit and restore resumes the co-op game |
| **9. Separate screens** | Game server, network interface port and thin client (Design §6) | Laura and her brother each play from their own terminal, seeing only their own hero's view |
| **10. Rented server** *(optional)* | Server runs on a small rented machine | Either player can start or resume a game with Laura's Mac off |
| **Later** | Revival route, giving items, shops, pets, quests, the Amulet, scoring | Each gets its own mini-design first |

## Testing

Laura works in test automation, so tests come first.

- **Golden master:** a fixed RNG seed plus a fixed keystroke script, driven through a
  pseudo-terminal (for example Python `pexpect`), saving the final dumplog or screen.
  Any unintended single-player change shows up as a diff.
- **Lua tests:** extend `test/` for co-op behaviour where wizard-mode Lua can reach it
  (spawning monsters, positions).
- **Swap round-trip:** activate hero 0, then 1, then 0. Every per-hero field must
  match exactly.
- **Deterministic co-op scripts** for each phase's "done when" checks.

[OPEN] How to fix the RNG seed for tests: check whether 5.0 exposes a way. Otherwise
add a debug-only option that calls `set_random()` with a fixed value.

## Decisions

| # | Question | Default (change freely) | Status |
|---|---|---|---|
| 1 | Approach | True two-hero co-op, built hotseat-first | Decided |
| 2 | Where the code lives | GitHub fork of `NetHack/NetHack`; Laura works on her Mac with Claude Code | Decided |
| 3 | How the brother connects | **Separate screens per player** (client–server, Design §6), with Laura hosting at first; possibly move the server to a rented machine later. Hotseat is only a development stepping stone | Decided |
| 4 | When one hero dies | **First:** game continues, the dead player watches (spectator view), game over when both are dead. **Later:** add a revival route (design TBD, e.g. corpse + co-aligned altar). Keep the dead hero's state and corpse so revival can be added without a save-format break | Decided |
| 5 | Max players | 2 | Decided |
| 6 | Character creation | Each player picks their own role and race; **both must share one alignment** (Player 2's choices are filtered to Player 1's alignment). **The Quest belongs to Player 1's role**: only P1 can be accepted by the leader; P2 can enter and help. A second Quest branch is a far-future idea | Decided |
| 7 | Bones | Off when more than one hero | Decided |
| 8 | Pets | **Each hero gets their own starting pet.** Every tame monster records an owner hero (starting pets and anything tamed later); pets follow, guard and fetch for their owner. Needs a save-format change, which is approved | Decided |

## Licence

NetHack is under the NetHack General Public License. A public or private fork is fine.
Keep the licence and copyright headers intact.
