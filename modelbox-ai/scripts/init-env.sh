#!/bin/sh
# Create modelbox-ai/.env from .env.example with freshly generated secrets.
#
# JWT_SECRET, ENCRYPTION_KEY and POSTGRES_PASSWORD each get 32 random bytes as
# 64 hex characters: long enough for the settings check, and URL-safe, since
# the database password is interpolated into a DSN.
#
# Refuses to overwrite an existing .env. Replacing ENCRYPTION_KEY makes every
# stored connection secret unreadable, and replacing POSTGRES_PASSWORD locks
# the appliance out of its own database volume, so there is no --force.
#
# Prints the names of what it generated, never the values.
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
example="$root/.env.example"
target="$root/.env"
generated="JWT_SECRET ENCRYPTION_KEY POSTGRES_PASSWORD"

hex_secret() {
    od -An -tx1 -N32 /dev/urandom | tr -d ' \n'
}

# guard:begin
if [ -e "$target" ]; then
    echo "$target already exists; refusing to overwrite it. Its secrets protect existing data. Remove it yourself only if you mean to start over." >&2
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
awk -v jwt="$(hex_secret)" -v enc="$(hex_secret)" -v pg="$(hex_secret)" '
    /^JWT_SECRET=/        { print "JWT_SECRET=" jwt; next }
    /^ENCRYPTION_KEY=/    { print "ENCRYPTION_KEY=" enc; next }
    /^POSTGRES_PASSWORD=/ { print "POSTGRES_PASSWORD=" pg; next }
    { sub(/\r$/, ""); print }
' "$example" > "$target"

echo "Wrote $target with generated JWT_SECRET, ENCRYPTION_KEY, POSTGRES_PASSWORD."
