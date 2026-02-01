FROM node:20-alpine

WORKDIR /app

# Copy package files first (for better layer caching)
COPY package*.json ./

# Install dependencies with BuildKit cache mount for faster rebuilds
# This caches npm packages between builds
RUN --mount=type=cache,target=/root/.npm \
    npm install --no-audit

# Copy source code (this layer only rebuilds when source changes)
COPY . .

# Expose port
EXPOSE 5173

# Start development server
# Note: Vite reads VITE_* env vars from process environment when dev server starts
CMD ["sh", "-c", "npm run dev"]
