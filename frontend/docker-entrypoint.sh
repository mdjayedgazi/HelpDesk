#!/bin/sh
set -eu

: "${API_ORIGIN:?API_ORIGIN must be set to the public backend origin}"

API_ORIGIN="${API_ORIGIN%/}"

# Keep the origin out of Nginx configuration if it could inject directives.
case "$API_ORIGIN" in
    https://?*) ;;
    *)
        echo "API_ORIGIN must use https:// in production" >&2
        exit 1
        ;;
esac
case "$API_ORIGIN" in
    *[[:space:]\"\']*)
        echo "API_ORIGIN contains invalid characters" >&2
        exit 1
        ;;
    *[?#]*)
        echo "API_ORIGIN must be an origin without a query or fragment" >&2
        exit 1
        ;;
    https://*/*)
        echo "API_ORIGIN must be an origin without a path" >&2
        exit 1
        ;;
esac

CLERK_FAPI_ORIGIN="${CLERK_FAPI_ORIGIN:-https://*.clerk.accounts.dev}"
case "$CLERK_FAPI_ORIGIN" in
    https://?*) ;;
    *)
        echo "CLERK_FAPI_ORIGIN must use https://" >&2
        exit 1
        ;;
esac
case "$CLERK_FAPI_ORIGIN" in
    *[[:space:]\"\']*)
        echo "CLERK_FAPI_ORIGIN contains invalid characters" >&2
        exit 1
        ;;
    *[?#]*)
        echo "CLERK_FAPI_ORIGIN must be an origin without a query or fragment" >&2
        exit 1
        ;;
    https://*/*)
        echo "CLERK_FAPI_ORIGIN must be an origin without a path" >&2
        exit 1
        ;;
esac

HSTS_MAX_AGE_SECONDS="${HSTS_MAX_AGE_SECONDS:-31536000}"
case "$HSTS_MAX_AGE_SECONDS" in
    *[!0-9]*|"")
        echo "HSTS_MAX_AGE_SECONDS must be a non-negative integer" >&2
        exit 1
        ;;
esac

if [ "${HSTS_ENABLED:-false}" = "true" ]; then
    printf 'add_header Strict-Transport-Security "max-age=%s; includeSubDomains" always;\n' \
        "$HSTS_MAX_AGE_SECONDS" > /etc/nginx/conf.d/hsts.inc
else
    : > /etc/nginx/conf.d/hsts.inc
fi

envsubst '${API_ORIGIN} ${CLERK_FAPI_ORIGIN}' \
    < /etc/nginx/nginx.conf.template \
    > /etc/nginx/conf.d/default.conf

exec nginx -g 'daemon off;'
