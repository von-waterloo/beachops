FROM node:22-alpine AS build

WORKDIR /webapp
COPY package.json package-lock.json ./
RUN npm install --global npm@11.6.2 && npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /webapp/dist /usr/share/nginx/html
EXPOSE 8080
