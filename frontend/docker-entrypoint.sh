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

# `envsubst` only reads exported variables. When Railway leaves
# CLERK_FAPI_ORIGIN unset, the shell default above must still reach the Nginx
# template or the Clerk-script/frame origins are silently dropped from the CSP.
export CLERK_FAPI_ORIGIN

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

# includeSubDomains is opt-in. It tells browsers to force HTTPS on *every*
# subdomain of this host, so enabling it before every subdomain has valid TLS
# can lock clients out of unrelated services. Only emit it when the operator has
# explicitly confirmed that readiness (HSTS_INCLUDE_SUBDOMAINS=true).
HSTS_INCLUDE_SUBDOMAINS="${HSTS_INCLUDE_SUBDOMAINS:-false}"
case "$HSTS_INCLUDE_SUBDOMAINS" in
    true|false) ;;
    *)
        echo "HSTS_INCLUDE_SUBDOMAINS must be 'true' or 'false'" >&2
        exit 1
        ;;
esac
# Nginx configuration output directory. Defaults to the image's real path; it is
# overridable only so the entrypoint's HSTS logic can be exercised by tests
# without writing to /etc. Production never sets it.
NGINX_CONF_DIR="${NGINX_CONF_DIR:-/etc/nginx/conf.d}"

if [ "${HSTS_ENABLED:-false}" = "true" ]; then
    if [ "$HSTS_INCLUDE_SUBDOMAINS" = "true" ]; then
        printf 'add_header Strict-Transport-Security "max-age=%s; includeSubDomains" always;\n' \
            "$HSTS_MAX_AGE_SECONDS" > "$NGINX_CONF_DIR/hsts.inc"
    else
        printf 'add_header Strict-Transport-Security "max-age=%s" always;\n' \
            "$HSTS_MAX_AGE_SECONDS" > "$NGINX_CONF_DIR/hsts.inc"
    fi
else
    : > "$NGINX_CONF_DIR/hsts.inc"
fi

# Template location. Defaults to the image path; overridable only for tests.
NGINX_TEMPLATE="${NGINX_TEMPLATE:-/etc/nginx/nginx.conf.template}"

envsubst '${API_ORIGIN} ${CLERK_FAPI_ORIGIN}' \
    < "$NGINX_TEMPLATE" \
    > "$NGINX_CONF_DIR/default.conf"

exec nginx -g 'daemon off;'
