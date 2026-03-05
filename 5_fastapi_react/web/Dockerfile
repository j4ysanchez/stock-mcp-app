# React / Vite dev server — hot reload enabled inside Docker.
FROM node:20-slim

WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .

EXPOSE 5173

# --host is passed as a CLI arg so Vite binds to 0.0.0.0 (already set in vite.config.ts,
# but the flag ensures it even when config is not picked up at startup).
CMD ["npm", "run", "dev"]
