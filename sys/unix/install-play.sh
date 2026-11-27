#!/bin/sh
# Copy the game built in ./playground to a separate folder for playing,
# so that rebuilding never touches your saved games.
#
# Every build's install step deletes and recreates ./playground (saves,
# bones and high scores included).  This copies only the program files to
# $NHPLAY (default ~/nethack-play) and leaves everything else there alone.
# If the save format changed (EDITLEVEL in include/patchlevel.h) and you
# have saved games, it stops: they wouldn't load.  Finish them first, or
# rerun with --force.
#
#   sys/unix/install-play.sh            # install or upgrade
#   ~/nethack-play/play                 # play (any nethack options work)
#
# See doc/features/build-macos.md.

set -eu

repo=$(cd "$(dirname "$0")/../.." && pwd)
src=$repo/playground
dest=${NHPLAY:-$HOME/nethack-play}
force=no
if [ "${1:-}" = "--force" ]; then
    force=yes
fi

if [ ! -x "$src/nethack" ]; then
    echo "No game in $src: build it first (doc/features/build-macos.md)." >&2
    exit 1
fi
editlevel=$(sed -n 's/^#define EDITLEVEL \([0-9][0-9]*\).*/\1/p' \
                "$repo/include/patchlevel.h")
version=$(git -C "$repo" describe --always --dirty 2>/dev/null || echo unknown)

mkdir -p "$dest/save"

# a game in progress (or one that crashed) leaves lock and level files
for f in "$dest"/*.[0-9] "$dest"/*.[0-9][0-9]; do
    if [ -e "$f" ]; then
        echo "A game seems to be running in $dest (found $(basename "$f"))." >&2
        echo "Finish or save it first.  After a crash, run" >&2
        echo "  cd $dest && NETHACKDIR=$dest ./recover -d . <file>" >&2
        exit 1
    fi
done

old=$(cat "$dest/.editlevel" 2>/dev/null || true)
saves=$(ls "$dest/save" 2>/dev/null || true)
if [ -n "$old" ] && [ "$old" != "$editlevel" ] && [ -n "$saves" ] \
   && [ "$force" = no ]; then
    echo "The save format changed (EDITLEVEL $old -> $editlevel)." >&2
    echo "These saved games in $dest/save would no longer load:" >&2
    echo "$saves" | sed 's/^/  /' >&2
    echo "Finish them with the installed version first, or rerun with" >&2
    echo "--force to upgrade anyway (they will be unusable)." >&2
    exit 1
fi

first=no
if [ ! -e "$dest/nethack" ]; then
    first=yes
fi

# program files: replaced (via a temporary name, so nothing is half-copied)
for f in nethack recover nhdat symbols license; do
    cp -p "$src/$f" "$dest/$f.new"
    mv -f "$dest/$f.new" "$dest/$f"
done

# game records: kept; created if missing (high scores carried over the
# first time)
for f in record logfile xlogfile livelog perm; do
    if [ ! -e "$dest/$f" ]; then
        if [ "$first" = yes ] && [ -s "$src/$f" ] && [ "$f" != perm ]; then
            cp -p "$src/$f" "$dest/$f"
        else
            : > "$dest/$f"
        fi
    fi
done

echo "$editlevel" > "$dest/.editlevel"
echo "$version" > "$dest/.version"

cat > "$dest/play" <<EOF
#!/bin/sh
# start the NetHack installed by $repo/sys/unix/install-play.sh
NETHACKDIR="$dest" exec "$dest/nethack" "\$@"
EOF
chmod +x "$dest/play"

if [ "$first" = yes ]; then
    echo "Installed NetHack ($version) in $dest."
else
    echo "Upgraded NetHack in $dest to $version; saved games kept."
fi
echo "Play with: $dest/play"
