#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pexpect==4.9.0", "pyte==0.8.2"]
# ///
"""Golden-master tests for single-player NetHack (Phase 0b).

Plays a scripted, seeded game through a pseudo-terminal, renders every
screen with a terminal emulator and compares the transcript with a stored
one.  Needs a build made with WANT_DETERMINISTIC=1
(doc/features/golden-master.md).

    test/golden/golden.py check   [scenario ...]   compare with expected/
    test/golden/golden.py update  [scenario ...]   re-record expected/
    test/golden/golden.py show     scenario [N]    print the last N screens
    test/golden/golden.py selftest [scenario]      same seed twice -> same,
                                                   other seed -> different
"""

import difflib
import faulthandler
import getpass
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import pexpect
import pyte

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PLAYGROUND = ROOT / "playground"
SCENARIOS = HERE / "scenarios"
LUA = HERE / "lua"          # copied into each run's playground (#wizloaddes)
EXPECTED = HERE / "expected"
OUT = HERE / "out"

TRACE = bool(os.environ.get("GOLDEN_TRACE"))  # log every key to stderr
faulthandler.register(signal.SIGUSR1)  # kill -USR1 <pid>: dump Python stack

COLS, ROWS = 80, 24
DRAIN = 0.05     # after the game says it waits for a key: read what's left
STEP_CAP = 20.0  # a single step taking longer than this is an error

# files the game needs from the install; everything else starts empty
INSTALL_FILES = ["nethack", "nhdat", "symbols", "license"]
EMPTY_FILES = ["record", "logfile", "xlogfile", "livelog", "perm"]

KEYNAMES = {"ret": "\r", "esc": "\x1b", "sp": " ", "tab": "\t", "bs": "\x7f"}
TOKEN = re.compile(r"<(ret|esc|sp|tab|bs|C-[a-z])>|(\S)")

# things that legitimately change between builds; masked before comparing
NORMALIZE = [
    (re.compile(r"built \w{3} [ \d]\d \d{4} \d\d:\d\d:\d\d"), "built <DATE>"),
    (re.compile(r"Copyright 1985-\d{4}"), "Copyright 1985-<YEAR>"),
]


class Scenario:
    """Header lines 'key: value' (seed, faketime, options), a line '---',
    then one step per line.

    Optional header 'wizard: yes' runs the game in wizard mode (-D), for
    scenarios that build their level with '#wizloaddes' from test/golden/lua.
    Wizard mode plays a different game for the same seed, so such a
    scenario is only comparable with itself.

    Step syntax: every non-space character is a key; spaces are ignored;
    <ret> <esc> <sp> <tab> <bs> <C-x> name special keys.  Lines starting
    with '//' are comments.  '!restart' starts the game again (after a save).
    """

    def __init__(self, path):
        self.name = path.stem
        self.header, self.steps = {}, []
        in_steps = False
        for lineno, raw in enumerate(path.read_text().splitlines(), 1):
            line = raw.rstrip()
            if not in_steps:
                if line == "---":
                    in_steps = True
                elif line and not line.startswith("//"):
                    k, _, v = line.partition(":")
                    self.header[k.strip()] = v.strip()
            elif line.strip() and not line.lstrip().startswith("//"):
                self.steps.append((lineno, line.strip()))
        for k in ("seed", "faketime", "options"):
            if k not in self.header:
                sys.exit(f"{path}: missing header '{k}:'")

    @property
    def wizard(self):
        return self.header.get("wizard", "no").lower() in ("yes", "1", "true")

    def epoch(self):
        dt = datetime.fromisoformat(self.header["faketime"].replace("Z", "+00:00"))
        return int(dt.astimezone(timezone.utc).timestamp())


def keys_of(step):
    out = []
    for name, ch in TOKEN.findall(step):
        if name.startswith("C-"):
            out.append(chr(ord(name[2]) & 0x1F))
        elif name:
            out.append(KEYNAMES[name])
        else:
            out.append(ch)
    return out


def allow_wizard():
    """Wizard mode needs the login name in WIZARDS in the compiled-in
    sysconf (playground/sysconf), which every 'make install' resets."""
    conf = PLAYGROUND / "sysconf"
    user = getpass.getuser()
    lines = conf.read_text().splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.startswith("WIZARDS="):
            names = line[len("WIZARDS="):].split()
            if user in names or "*" in names:
                return
            lines[i] = line.rstrip("\n") + f" {user}\n"
            conf.write_text("".join(lines))
            print(f"golden: added {user} to WIZARDS in {conf}", file=sys.stderr)
            return
    sys.exit(f"{conf}: no WIZARDS= line; can't enable wizard mode")


def make_playground(work):
    pg = work / "playground"
    pg.mkdir()
    (pg / "save").mkdir()
    for f in INSTALL_FILES:
        src = PLAYGROUND / f
        if not src.exists():
            sys.exit(f"missing {src}: build and install first"
                     " (see doc/features/build-macos.md)")
        shutil.copy2(src, pg / f)
    for f in EMPTY_FILES:
        (pg / f).touch()
    for f in LUA.glob("*.lua"):   # the game looks for lua files in its dir
        shutil.copy2(f, pg / f.name)
    (work / "home").mkdir()
    return pg


class Game:
    def __init__(self, scen, pg, home, seed):
        self.env = {
            "PATH": "/usr/bin:/bin",
            "HOME": str(home),          # keeps ~/.nethackrc out
            "TERM": "xterm-256color",
            "TZ": "UTC",                # night()/midnight() use local time
            "LC_ALL": "C",
            "NETHACKDIR": str(pg),      # fresh playground: no bones, no saves
            "NETHACKOPTIONS": scen.header["options"],
            "NETHACK_SEED": str(seed),
            "NETHACK_FAKETIME": str(scen.epoch()),
            # the game appends a byte here each time it waits for a key
            "NETHACK_INPUT_SYNC": str(pg / "inputsync"),
        }
        self.args = ["-D"] if scen.wizard else []
        self.pg = pg
        self.sync = pg / "inputsync"
        self.waits = 0
        self.screen = pyte.Screen(COLS, ROWS)
        self.stream = pyte.Stream(self.screen)
        self.child = None

    def start(self):
        self.waits = self.sync_count()  # a restart appends to the same file
        self.child = pexpect.spawn(str(self.pg / "nethack"), self.args, env=self.env,
                                   cwd=str(self.pg), dimensions=(ROWS, COLS),
                                   encoding="utf-8", codec_errors="replace")
        self.screen.reset()
        return self.settle()

    def sync_count(self):
        try:
            return self.sync.stat().st_size
        except FileNotFoundError:
            return 0

    def settle(self):
        """Read output until the game is waiting for the next key, which it
        signals through NETHACK_INPUT_SYNC (a pause in output isn't proof:
        a busy game can pause mid-run).  Returns False if the game exited."""
        start = time.monotonic()
        while True:
            try:
                self.stream.feed(self.child.read_nonblocking(65536, timeout=0.02))
            except pexpect.TIMEOUT:
                pass
            except pexpect.EOF:
                self.child.close()
                return False
            n = self.sync_count()
            if n > self.waits:
                self.waits = n
                break
            if time.monotonic() - start > STEP_CAP:
                if not self.sync.exists():
                    raise RuntimeError("the game never signalled NETHACK_INPUT_SYNC:"
                                       " rebuild with WANT_DETERMINISTIC=1")
                raise RuntimeError("game never waited for input")
        # the screen was flushed before the signal; collect what's buffered
        while True:
            try:
                self.stream.feed(self.child.read_nonblocking(65536, timeout=DRAIN))
            except pexpect.TIMEOUT:
                return True
            except pexpect.EOF:
                self.child.close()
                return False

    def alive(self):
        return self.child is not None and self.child.isalive()

    def send(self, key):
        t0 = time.monotonic()
        self.child.send(key)
        ok = self.settle()
        if TRACE:
            print(f"[trace] {time.strftime('%H:%M:%S')} key {key!r} "
                  f"{time.monotonic() - t0:.2f}s", file=sys.stderr, flush=True)
        return ok

    def snapshot(self):
        lines = [line.rstrip() for line in self.screen.display]
        while lines and not lines[-1]:
            lines.pop()
        text = "\n".join(lines)
        for pat, repl in NORMALIZE:
            text = pat.sub(repl, text)
        cur = self.screen.cursor
        return f"{text}\n[cursor {cur.x},{cur.y}]"


def run(scen, seed=None):
    """Play the scenario; return the transcript as one string."""
    seed = int(scen.header["seed"]) if seed is None else seed
    out = [f"scenario {scen.name}  seed {seed}  faketime {scen.header['faketime']}"]
    if scen.wizard:
        allow_wizard()
    with tempfile.TemporaryDirectory(prefix="nhgolden-") as tmp:
        work = Path(tmp)
        game = Game(scen, make_playground(work), work / "home", seed)
        game.start()
        out += ["", "=== start", game.snapshot()]
        for lineno, step in scen.steps:
            if step == "!restart":
                if game.alive():
                    out.append("!! restart requested but game still running")
                    game.child.terminate(force=True)
                game.start()
            elif step.startswith("!"):
                sys.exit(f"{scen.name}:{lineno}: unknown directive {step}")
            else:
                if not game.alive():
                    out.append(f"!! line {lineno}: game exited before this step")
                    break
                try:
                    for key in keys_of(step):
                        if not game.send(key):
                            break
                except RuntimeError as exc:
                    # a script that doesn't fit the game (like selftest's
                    # other seed): record it and stop this run
                    out += ["", f"=== line {lineno}: {step}",
                            f"!! the game stopped responding: {exc}"]
                    break
            out += ["", f"=== line {lineno}: {step}", game.snapshot()]
            if not game.alive():
                out.append("[game exited]")
        if game.alive():
            out.append("!! game still running at end of scenario")
            game.child.terminate(force=True)
    return "\n".join(out) + "\n"


def scenarios(names):
    if not names:
        return [Scenario(p) for p in sorted(SCENARIOS.glob("*.keys"))]
    return [Scenario(SCENARIOS / f"{n}.keys") for n in names]


def cmd_check(names):
    OUT.mkdir(exist_ok=True)
    failed = 0
    for scen in scenarios(names):
        exp_path = EXPECTED / f"{scen.name}.txt"
        actual = run(scen)
        (OUT / f"{scen.name}.txt").write_text(actual)
        if not exp_path.exists():
            print(f"NEW   {scen.name}: no expected output; run 'update'")
            failed += 1
            continue
        expected = exp_path.read_text()
        if actual == expected:
            print(f"PASS  {scen.name}")
            continue
        failed += 1
        print(f"FAIL  {scen.name}  (actual in {OUT / (scen.name + '.txt')})")
        diff = list(difflib.unified_diff(expected.splitlines(), actual.splitlines(),
                                         "expected", "actual", lineterm="", n=3))
        print("\n".join(diff[:120]))
        if len(diff) > 120:
            print(f"... {len(diff) - 120} more diff lines")
    return 1 if failed else 0


def cmd_update(names):
    EXPECTED.mkdir(exist_ok=True)
    for scen in scenarios(names):
        (EXPECTED / f"{scen.name}.txt").write_text(run(scen))
        print(f"recorded {scen.name}")
    return 0


def cmd_show(args):
    scen = scenarios(args[:1])[0]
    count = int(args[1]) if len(args) > 1 else 1
    blocks = run(scen).split("\n\n=== ")
    print("\n\n=== ".join(blocks[-count:]))
    return 0


def cmd_selftest(names):
    scen = scenarios(names[:1] or ["basic"])[0]
    seed = int(scen.header["seed"])
    a, b, c = run(scen), run(scen), run(scen, seed + 1)
    ok = True
    if a != b:
        ok = False
        print("FAIL  same seed gave different transcripts:")
        print("\n".join(list(difflib.unified_diff(a.splitlines(), b.splitlines(),
                                                  "run1", "run2", lineterm=""))[:60]))
    else:
        print("PASS  same seed twice: identical")
    strip = lambda t: t.split("\n", 1)[1]  # drop header line naming the seed
    if strip(a) == strip(c):
        ok = False
        print("FAIL  different seed gave the same transcript"
              " (is this a WANT_DETERMINISTIC build?)")
    else:
        print("PASS  different seed: different game")
    return 0 if ok else 1


def stay_awake():
    """An unattended Mac sleeps mid-run, freezing the game and this script
    for minutes (looks like a hang).  Keep it awake while this process
    lives: -i (idle sleep) is ignored during a "dark wake", so also -s
    (system sleep), which macOS honours on AC power only."""
    if sys.platform == "darwin" and shutil.which("caffeinate"):
        subprocess.Popen(["caffeinate", "-i", "-s", "-w", str(os.getpid())],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main(argv):
    stay_awake()
    cmds = {"check": cmd_check, "update": cmd_update,
            "show": cmd_show, "selftest": cmd_selftest}
    if not argv or argv[0] not in cmds:
        print(__doc__)
        return 2
    return cmds[argv[0]](argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
