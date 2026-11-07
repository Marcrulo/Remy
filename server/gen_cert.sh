#!/usr/bin/env bash
# Generate a self-signed cert valid for localhost + the given LAN IPs (default: auto-detect).
set -euo pipefail
cd "$(dirname "$0")"
IPS="${*:-$(hostname -I | tr ' ' '\n' | grep -E '^[0-9]+\.' | tr '\n' ' ')}"
SAN="DNS:localhost,IP:127.0.0.1"
for ip in $IPS; do SAN="$SAN,IP:$ip"; done
mkdir -p certs
openssl req -x509 -newkey rsa:2048 -nodes -days 825 \
  -keyout certs/key.pem -out certs/cert.pem \
  -subj "/CN=remy.local" -addext "subjectAltName=$SAN"
echo "Cert written to server/certs (SAN: $SAN)"
