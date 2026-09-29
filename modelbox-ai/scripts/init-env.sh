#!/bin/sh
# Create modelbox-ai/.env from .env.example with freshly generated secrets.
#
# JWT_SECRET, ENCRYPTION_KEY, POSTGRES_PASSWORD and MODELBOX_APP_DB_PASSWORD
# each get 32 random bytes as 64 hex characters: long enough for the settings
# check, and URL-safe, since the database passwords are interpolated into DSNs.
#
# Refuses to overwrite an existing .env. Replacing ENCRYPTION_KEY makes every
# stored connection secret unreadable, and replacing POSTGRES_PASSWORD locks
# the appliance out of its own database volume, so there is no --force.
#
# --add-missing is for upgrades: it appends only the secrets an existing .env
# lacks, never changes a key already present (even an empty one), and never
# creates the file.
#
# Prints the names of what it generated, never the values.
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
example="$root/.env.example"
target="$root/.env"
generated="JWT_SECRET ENCRYPTION_KEY POSTGRES_PASSWORD MODELBOX_APP_DB_PASSWORD"

hex_secret() {
    od -An -tx1 -N32 /dev/urandom | tr -d ' \n'
}

if [ "${1:-}" = "--add-missing" ]; then
    if [ ! -e "$target" ]; then
        echo "$target does not exist; run without --add-missing to create it." >&2
        exit 1
    fi
    added=""
    for name in $generated; do
        # keep:begin
        if grep -q "^$name=" "$target"; then
            continue
        fi
        # keep:end
        # Start on a new line if the file does not end with one.
        if [ -s "$target" ] && [ -n "$(tail -c 1 "$target")" ]; then
            printf '\n' >> "$target"
        fi
        printf '%s=%s\n' "$name" "$(hex_secret)" >> "$target"
        added="$added $name"
    done
    if [ -z "$added" ]; then
        echo "Nothing to add; $target already declares $generated."
    else
        echo "Added to $target:$added."
    fi
    exit 0
fi

# guard:begin
if [ -e "$target" ]; then
    echo "$target already exists; refusing to overwrite it. Its secrets protect existing data. Remove it yourself only if you mean to start over, or use --add-missing to add only what it lacks." >&2
    exit 1
fi
# noclobber makes the write below fail if the file appeared since the check.
set -o noclobber
# guard:end

for name in $generated; do
    count=$(grep -c "^$name=" "$example" || true)
    if [ "$count" -ne 1 ]; then
        echo "$example must declare $name exactly once; found $count." >&2
        exit 1
    fi
done

umask 077
awk -v jwt="$(hex_secret)" -v enc="$(hex_secret)" -v pg="$(hex_secret)" -v app="$(hex_secret)" '
    /^JWT_SECRET=/               { print "JWT_SECRET=" jwt; next }
    /^ENCRYPTION_KEY=/           { print "ENCRYPTION_KEY=" enc; next }
    /^POSTGRES_PASSWORD=/        { print "POSTGRES_PASSWORD=" pg; next }
    /^MODELBOX_APP_DB_PASSWORD=/ { print "MODELBOX_APP_DB_PASSWORD=" app; next }
    { sub(/\r$/, ""); print }
' "$example" > "$target"

echo "Wrote $target with generated $generated."
