#!/bin/bash
set -e

curl -k https://127.0.0.1/health \
  --key /etc/nginx/ssl/tls.key \
  --cacert /etc/nginx/ssl/tls.ca-chain.crt \
  --cert /etc/nginx/ssl/tls.crt

exit 0