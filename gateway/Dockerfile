FROM openresty/openresty:alpine

RUN apk add --no-cache git openssl-dev luarocks && \
    luarocks install lua-resty-string || true && \
    luarocks install lua-resty-hmac || true

RUN mkdir -p /var/log/nginx && \
    mkdir -p /etc/nginx

COPY nginx.conf /usr/local/openresty/nginx/conf/nginx.conf
COPY jwt_auth.lua /etc/nginx/jwt_auth.lua

EXPOSE 80

CMD ["/usr/local/openresty/bin/openresty", "-g", "daemon off;"]
