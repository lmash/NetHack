# Building vanilla 5.0 on macOS (Phase 0)

Verified 2026-11-23 on the `features` branch (tag `NetHack-5.0.0_Released`
plus docs only), macOS 26 (Darwin 25.6), Apple Command Line Tools, Homebrew
installed. Builds on the notes in `doc/coop/build-macos.md` on the `coop`
branch.

## One-time setup

    cd sys/unix && sh setup.sh hints/macOS.500 && cd ../..
    make fetch-lua            # lua-5.4.8 into lib/ (already present here)

## Build

    make clean
    make -j8 HAVE_HOMEBREW=0 WANT_WIN_TTY=1 WANT_WIN_CURSES=1 WANT_SOURCE_INSTALL=1 all

- About 12 s wall time on 8 cores. 187 compile steps. The only warning is a
  harmless `ld: warning: ignoring duplicate libraries: '-lncurses'`.
- `WANT_SOURCE_INSTALL=1` installs into `./playground/` (untracked).
- `HAVE_HOMEBREW=0` is required when Homebrew's ncurses is installed. Without
  it, the curses link fails on `_wrefresh$NCURSES60`, because the hints file
  passes Homebrew's include dir as a link flag. Left unfixed to stay vanilla.
- For golden-master runs, add `WANT_DETERMINISTIC=1` (test hooks, inert
  unless `NETHACK_SEED`/`NETHACK_FAKETIME` are set; see `determinism.md`).
  Fine to keep on for everyday builds.
- **After any change to `sys/unix/hints/`, rerun `setup.sh`.** The Makefiles
  are generated from the hints, so otherwise the change is silently ignored.
  (Found when `WANT_DETERMINISTIC=1` built fine but `NETHACK_SEED` did nothing.)
  Check with `strings playground/nethack | grep NETHACK_SEED`.
- Pass the same variables every time. Changing flags needs `make clean`,
  because make doesn't track them. **The playground is shared with the
  `coop` branch:** after building there, run `make clean` and rebuild here.

## Run

    ./playground/nethack            # tty
    ./playground/nethack -wcurses   # curses

Wizard mode (`-D`, needed for `test/*.lua` via `#wizloadlua`) needs your
username in `WIZARDS=` in `playground/sysconf` (default `root games`).
**Every build reinstalls `sysconf` and resets this edit**, so redo it after
each build (`sed -i '' 's/^WIZARDS=root games$/& <you>/' playground/sysconf`).

## Smoke test (scripted, isolated)

Run a copy of the playground through a pseudo-terminal, with `NETHACKDIR`
pointing at the copy and an empty `HOME`:

    NETHACKOPTIONS="name:smoke,role:valkyrie,race:human,gender:female,align:lawful,!tips,!tutorial,!legacy,!autopickup,time"

Result: welcome screen, `s` (search) moves `T:1` to `T:2`, and `#quit` writes
`version=5.0.0 death=quit turns=2` to the copy's `xlogfile`.

## 5.0 gotchas for scripting

- 5.0 asks "Do you want a tutorial?" at start. Use `!tutorial`.
- `-g` is no longer gender. Set the character with options.
- `time` must be on for `T:` to appear on the status line.
- tty redraws only changed cells, so read screens through a terminal emulator
  (`pyte`), not the raw byte stream.
