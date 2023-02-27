#!/bin/sh

# Check if certbot command was already run
if [[ -z "${CERTBOT_RUN}" ]]; then
  # Run certbot command
  certbot run -n --nginx --agree-tos -d no.dojotunnel.online  -m bhartford419@gmail.com --redirect
  export CERTBOT_RUN=true
fi

# Reload nginx
#nginx -s reload

#lsof -i :80
#lsof -i :443
#systemctl restart nginx
# Keep container running
#nginx -g 'daemon off;'
