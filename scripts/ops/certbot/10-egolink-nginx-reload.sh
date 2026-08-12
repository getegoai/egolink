#!/usr/bin/env bash
set -eu

/usr/sbin/nginx -t
/usr/bin/systemctl reload nginx
