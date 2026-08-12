# build context = repo root
FROM node:20-alpine AS build
WORKDIR /app
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
ARG VITE_GOOGLE_CLIENT_ID=
ARG VITE_REQUIRE_EMAIL_VERIFICATION=false
ARG VITE_INGEST_PUBLIC_URL=http://localhost:8082
ENV VITE_GOOGLE_CLIENT_ID=$VITE_GOOGLE_CLIENT_ID
ENV VITE_REQUIRE_EMAIL_VERIFICATION=$VITE_REQUIRE_EMAIL_VERIFICATION
ENV VITE_INGEST_PUBLIC_URL=$VITE_INGEST_PUBLIC_URL
RUN npm run build

FROM nginx:alpine
COPY web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
