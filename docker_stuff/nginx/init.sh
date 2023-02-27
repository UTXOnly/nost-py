#!/bin/sh

# Check if certbot command was already run
if [[ -z "${CERTBOT_RUN}" ]]; then
  # Run certbot command
  certbot run -n --nginx --agree-tos -d nostrtest.dojotunnel.online  -m bhartford419@gmail.com --redirect
  export CERTBOT_RUN=true
fi

# Reload nginx
nginx -s reload

# Keep container running
nginx -g 'daemon off;'
