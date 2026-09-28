FROM nginx:stable-alpine

RUN apk add --no-cache openssl && mkdir /etc/nginx/ssl
COPY 40-certificates.sh /docker-entrypoint.d/
COPY default.conf /etc/nginx/conf.d/
