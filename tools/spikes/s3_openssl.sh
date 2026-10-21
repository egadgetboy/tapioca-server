#!/bin/sh
# Spike S-3 for "The server proves who it is" (the apps repo's
# docs/threat-models/server-proof.md): what the image's own openssl and nice
# do, run inside the image people get. Prints one line per check; exits 1 on
# any failure. Makes throwaway keys in a temporary folder and deletes them.
set -u
fail=0
say() { echo "$1"; }
bad() { echo "FAIL: $1"; fail=1; }
dir=$(mktemp -d)
trap 'rm -rf "$dir"' EXIT
[ -x /usr/bin/openssl ] && say "openssl at /usr/bin/openssl" || bad "no /usr/bin/openssl"
[ -x /usr/bin/nice ] && say "nice at /usr/bin/nice" || bad "no /usr/bin/nice"
v=$(/usr/bin/openssl version)
say "version: $v"
case "$v" in "OpenSSL 3."*) ;; *) bad "not OpenSSL 3: $v" ;; esac
umask 022
start=$(date +%s%N)
/usr/bin/openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -pkeyopt rsa_keygen_pubexp:65537 -out "$dir/k.pem" 2>/dev/null || bad "genpkey failed"
say "genpkey: $(( ($(date +%s%N) - start) / 1000000 )) ms"
mode=$(stat -c %a "$dir/k.pem")
[ "$mode" = 600 ] && say "key file mode 600 under umask 022" || bad "key file mode $mode"
head -1 "$dir/k.pem" | grep -q '^-----BEGIN PRIVATE KEY-----$' && say "unencrypted PKCS#8" || bad "not BEGIN PRIVATE KEY"
/usr/bin/openssl pkey -in "$dir/k.pem" -pubout -outform DER -out "$dir/pub.der" 2>/dev/null
size=$(stat -c %s "$dir/pub.der")
[ "$size" = 422 ] && say "public key 422 bytes" || bad "public key $size bytes"
printf 'tapioca/1 server-proof\n{"spike":true}' > "$dir/msg"
env -i PATH=/usr/bin /usr/bin/nice -n 10 /usr/bin/openssl dgst -sha256 -sign "$dir/k.pem" -passin pass: -out "$dir/sig" "$dir/msg" || bad "signing through nice failed"
[ "$(stat -c %s "$dir/sig")" = 384 ] && say "signature 384 bytes" || bad "signature size"
/usr/bin/openssl pkey -pubin -inform DER -in "$dir/pub.der" -out "$dir/pub.pem" 2>/dev/null
/usr/bin/openssl dgst -sha256 -verify "$dir/pub.pem" -signature "$dir/sig" "$dir/msg" >/dev/null 2>&1 && say "signature checks" || bad "signature doesn't check"
start=$(date +%s%N)
i=0
while [ $i -lt 20 ]; do
    env -i PATH=/usr/bin /usr/bin/nice -n 10 /usr/bin/openssl dgst -sha256 -sign "$dir/k.pem" -passin pass: -out "$dir/s$i" "$dir/msg" || bad "sign $i"
    i=$((i + 1))
done
say "20 signatures through nice, process start included: $(( ($(date +%s%N) - start) / 20000 )) us each"
/usr/bin/openssl pkey -in "$dir/k.pem" -aes256 -passout pass:secret -out "$dir/enc.pem" 2>/dev/null
if printf 'secret\nrest' | /usr/bin/openssl dgst -sha256 -sign "$dir/enc.pem" -passin pass: -out "$dir/encsig" 2>/dev/null; then
    bad "-passin pass: signed with an encrypted key"
else
    say "-passin pass: with an encrypted key fails closed"
fi
env -i PATH=/usr/bin /usr/bin/nice -n 10 /usr/bin/no-such-openssl 2>/dev/null; code=$?
say "nice with a missing program exits $code"
[ $code -ge 125 ] && [ $code -le 127 ] || bad "a missing program's exit $code isn't 125 to 127"
say "arch: $(uname -m)"
exit $fail
