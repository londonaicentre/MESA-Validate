#!/bin/sh

# use mounted certificates if present, otherwise a self-signed one
if [ -f /etc/nginx/certs/cert.pem ]; then
  ln -sf /etc/nginx/certs/cert.pem /etc/nginx/certs/key.pem /etc/nginx/ssl/
else
  openssl req -x509 -nodes -newkey rsa:2048 -subj "/CN=localhost" \
    -keyout /etc/nginx/ssl/key.pem -out /etc/nginx/ssl/cert.pem
fi
