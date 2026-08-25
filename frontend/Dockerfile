FROM node:20-alpine
WORKDIR /ui
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG VITE_API_PROXY=http://backend:8000
ENV VITE_API_PROXY=$VITE_API_PROXY
RUN npm run build
EXPOSE 5173
CMD ["npx", "vite", "preview", "--host", "0.0.0.0", "--port", "5173"]
