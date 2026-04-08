FROM node:22-bookworm-slim

# Set environment variables for optimization
ENV NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=development

WORKDIR /app

# Install dependencies first for better layer caching
COPY package.json package-lock.json* ./
RUN npm install && npm cache clean --force

# Copy application code
COPY . .

CMD ["npm", "run", "dev"]
