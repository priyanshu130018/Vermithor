FROM nginx:alpine

RUN mkdir -p /var/log/nginx /etc/nginx

COPY nginx.conf /etc/nginx/nginx.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
