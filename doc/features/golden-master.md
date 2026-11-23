# Golden-master test (Phase 0b)

A seeded, scripted single-player game is played through a pseudo-terminal.
Every screen is rendered with a terminal emulator (`pyte`) and the whole
transcript is compared with a stored one. Any change to gameplay, including
one extra or missing `rn2()` call, shows up as a diff. **It must pass on every
commit** (CLAUDE.md ground rule 1).

Ported from the `coop` branch with the co-op modes removed (swaptest, second
terminal, colour snapshots).

## Run it

Build with the test hooks (see `build-macos.md`; rerun `setup.sh` first if the
hints changed):

    make -j8 HAVE_HOMEBREW=0 WANT_WIN_TTY=1 WANT_WIN_CURSES=1 \
         WANT_SOURCE_INSTALL=1 WANT_DETERMINISTIC=1 all

Then:

    test/golden/golden.py check              # PASS/FAIL per scenario, diff on failure
    test/golden/golden.py update             # re-record expected/ (on purpose only)
    test/golden/golden.py selftest           # same seed twice -> identical;
                                             # other seed -> different
    test/golden/golden.py show basic 3       # print the last 3 screens

The only requirement is `uv`: the script pins `pexpect` and `pyte` itself.
`basic` takes about 18 s. `GOLDEN_TRACE=1` logs each key and its timing to
stderr. `kill -USR1 <pid>` dumps the Python stack. Failed runs leave the actual
transcript in `test/golden/out/` (ignored by git).

**`WANT_DETERMINISTIC=1` is safe to keep on for everyday builds.** The hooks do
nothing unless `NETHACK_SEED` / `NETHACK_FAKETIME` / `NETHACK_INPUT_SYNC` are
set. Switching the flag on or off needs `make clean`.

## How determinism is achieved

Background: `determinism.md`. With `NH_DETERMINISTIC` compiled in:

- `NETHACK_SEED=<n>`: `sys_random_seed()` (`sys/unix/unixmain.c`) returns
  splitmix64 of n and a call counter. It leaves `has_strong_rngseed` FALSE, so
  `reseed_random()` is a no-op and a run is one continuous random stream.
  Per-level reseeding would hide drift. On `coop`, an extra `rn2()` in
  `u_init()` passed the test while reseeding was on, because `mklev()`
  reseeded right after it.
- `NETHACK_FAKETIME=<epoch>`: `getnow()` (`src/calendar.c`) returns it, and
  `ubirthday` (`src/u_init.c`) uses `getnow()`.
- `NETHACK_INPUT_SYNC=<file>`: `tty_nhgetch()` appends a byte each time it is
  about to wait for a key, after flushing the screen. The harness sends a key,
  waits for the count to rise, then reads the already-buffered output. Waiting
  for silence instead caught half-drawn screens when the machine was busy.
- The harness sets `TZ=UTC`, an empty `HOME` (so `~/.nethackrc` is ignored),
  the full option string in `NETHACKOPTIONS`, `TERM=xterm-256color`, an 80x24
  terminal, and a fresh copy of the playground for each run via `NETHACKDIR`
  (so no bones, saves or scores carry over).
- Masked before comparing: build date and copyright year.

## Verified (2026-11-23, features branch)

- `basic` on vanilla gives a transcript byte-identical to the one recorded on
  `coop`.
- `selftest`: PASS (same seed twice gives identical output, seed+1 a different
  game).
- Mutation: one extra `(void) rn2(2)` in `u_init_misc()` makes `check` FAIL
  from the first screen. Reverted, it passes again.
- Load: passes with every CPU busy under `nice -n 15`, in the same 18 s.
- `shop`: `selftest` passes. An extra `rn2()` in `get_cost()` (`src/shk.c`)
  makes `shop` FAIL while `basic` still passes. Reverted, both pass. `check`
  for both takes about 35 s.

## Writing scenarios

`test/golden/scenarios/<name>.keys` holds header lines (`seed:`, `faketime:`,
`options:`), a line `---`, then one step per line. In a step, every non-space
character is a key, and `<ret> <esc> <sp> <tab> <bs> <C-x>` name special keys.
`//` starts a comment line. `!restart` starts the game again after a save. The
screen is recorded after each step.

Optional header `wizard: yes` runs the game with `-D`. The harness then adds
your login name to `WIZARDS` in `playground/sysconf` (which every build
resets), and prints a note when it does. `test/golden/lua/*.lua` is copied
into each run's playground, where `#wizloadlua` and `#wizloaddes` look for
files. Wizard mode asks two extra questions: "keep the save file?" on
restore and "Dump core?" on quit.

**Scenarios must never use the F1/F2 commands**, so the transcripts stay
comparable with vanilla.

Build a scenario a few lines at a time with `show`, reading the screen before
writing the next keys. Gotchas:

- `--More--` (a red `>>` in 5.0 tty) accepts only Return, Space or Esc. Other
  keys are dropped. When a script goes wrong, it's usually a missed `<ret>`.
- Use `!tips` and `!tutorial`, or 5.0 asks extra questions. `-g` is not gender,
  so set the character with options.
- The faketime should avoid full or new moon, Friday 13th and night (`basic`
  uses Tuesday 2026-03-10 12:00 UTC).
- **Wizard mode (`-D`) plays a different game for the same seed.** It forces
  the name "wizard", and the starting stats differ. A seed or key sequence
  found in wizard mode does not carry over to normal play, so you can't use
  wizard mode to search for seeds (e.g. one with an early shop).
- Changing the seed, the options or any game code that touches the RNG means
  the script no longer fits the dungeon. Expect to rewrite it, not just
  re-record it.

## What `basic` covers

A Valkyrie with seed 42: walking and running; fights (jackal, goblin, kobold,
newt) with a pet helping; a dart trap; a pickup menu; wearing armour; a potion
of paralysis; travel (`_` with `<` and `>`); going downstairs (a new level, with
level 1 saved to disk); eating; save, exit and restore; going back upstairs (the
saved level reloaded); `i`, `^X`, `^O`, `\`; and quitting through all the
end-of-game screens.

## What `shop` covers

Wizard mode, seed 42. `#wizloaddes golden_shop` replaces Dlvl 1 with
`test/golden/lua/golden_shop.lua`: a lit room with an unlocked large box (an
unidentified scroll and potion), a locked chest (2 rubies), a 3-item pile, and
a corridor to a general store with random stock.

It covers: `:` on a square; `#loot` and taking one item out (names shown
unidentified); `#loot` on a locked chest; `#force` (it destroys the chest, and
the rubies spill onto the floor); walking onto a pile and `:`; picking up from
a pile; `#tip` onto the floor; the shopkeeper's greeting; goods priced on
standing and on pickup; `p` with no gold; dropping an unpaid item; selling two
items; buying with the proceeds; save and restore inside the shop; the sold
items for sale in a priced pile after restore; and quitting through the end
screens.

Findings:

- Prices of goods come from `doname_with_price()` (`src/objnam.c`) and
  `get_cost()`. `price_quote()` is only reached from `#chat` with a
  shopkeeper (`src/sounds.c`), so `shop` doesn't cover it.
- The end-of-game dungeon overview is **empty**, though the hero visited a
  shop. Likely cause: the level's `mapseen` record (which Ctrl-O and F1 use)
  isn't updated for a level replaced by `#wizloaddes`. Not investigated yet.
  Keep it in mind before using `#wizloaddes` levels to test F1.

## Known limits

- Wizard-mode scenarios (`shop`) are only comparable with themselves, not
  with a normal-mode game.

- tty only, macOS only so far. The hooks are in shared Unix code, so Linux
  should be easy.
- A sleeping Mac freezes runs: the test isn't hung, just paused. The harness
  runs `caffeinate`, but a closed lid still sleeps.
