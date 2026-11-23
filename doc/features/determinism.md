# Sources of nondeterminism (for the golden master)

Findings from reading the 5.0 source, 2026-11-22. 5.0 has **no built-in option
to fix the RNG seed**.

## RNG seeding

- Two ISAAC64 generators: `CORE` (`rn2`) and `DISP` (`rn2_on_display_rng`),
  in `src/rnd.c`.
- Every seed comes from `sys_random_seed()` (`sys/unix/unixmain.c`). That reads
  `/dev/urandom` (`DEV_RANDOM`, `include/unixconf.h`) and sets
  `has_strong_rngseed = TRUE`. It falls back to `time * pid`.
- Callers:
  - `init_random()` at startup: `src/options.c` (`initoptions_init`).
  - `reseed_random()`: before *and* after building every new level
    (`mklev()`, `src/mklev.c`) and on returning to a saved level (`goto_level()`,
    `src/do.c`). It is a no-op unless `has_strong_rngseed`.
  - So with `/dev/urandom` the RNG is reseeded on **every level change**.
    Fixing only the initial seed is not enough.
- `sys_random_seed()` is the single choke point for all of the above.

## Wall clock

- `getnow()` (`src/calendar.c`) drives `phase_of_the_moon()`, `friday_13th()`,
  `night()` and `midnight()`. These change gameplay and RNG call patterns:
  luck at full or new moon, undead at night, gremlins and so on
  (`src/allmain.c`).
- `ubirthday` is set with a direct `time()` call in `src/u_init.c`, not
  `getnow()`. It affects gameplay: shopkeeper names (`shknam.c`), a room-type
  choice (`mkroom.c`), T-shirt and apron text (`read.c`) and the bones pool
  (`files.c`).
- `urealtime` (play time) only appears in logs.

## Environment

- Bones files in the playground get loaded (using `rn2`) on new levels. Each
  run needs a clean playground.
- `~/.nethackrc` and the `NETHACKOPTIONS` variable change options.
- Terminal size and `TERM` change the layout.
- `NETHACKDIR`/`HACKDIR` env vars or `-d` select the playground. `SYSCF_FILE`
  is a compiled-in absolute path.

## What we did about it

See `golden-master.md` (this directory). In a `WANT_DETERMINISTIC=1` build, `NETHACK_SEED`
fixes the seed and turns off reseeding (one continuous stream per run, so
drift can't be hidden by a reseed). `NETHACK_FAKETIME` freezes `getnow()`
and `ubirthday`. The harness isolates the environment.
