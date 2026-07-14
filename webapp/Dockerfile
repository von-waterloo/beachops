FROM node:22-alpine AS build

ARG WEBAPP_BUILD_ID=dev
WORKDIR /webapp
COPY package.json package-lock.json ./
RUN npm install --global npm@11.6.2 && npm ci
COPY . .
RUN printf '%s\n' "$WEBAPP_BUILD_ID" > public/build-id.txt && npm run build

FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /webapp/dist /usr/share/nginx/html
EXPOSE 8080
