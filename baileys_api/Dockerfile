# ------------------------------------------------------
# Stage 1: Builder
# ------------------------------------------------------
FROM node:20-alpine AS builder

WORKDIR /app

# Install build dependencies
RUN apk add --no-cache \
    python3 \
    make \
    g++ \
    cairo-dev \
    jpeg-dev \
    pango-dev \
    giflib-dev \
    librsvg-dev \
    pixman-dev \
    git \ 
    openssl

# Copy dependency files first (for caching)
COPY package*.json ./
COPY engine-requirements.js ./
COPY prisma/ ./

# Install deps
RUN  npm install --ignore-scripts --legacy-peer-deps

# Copy full project
COPY . .

# Generate Prisma client
RUN npx prisma generate



# Build project
RUN npm run build



# ------------------------------------------------------
# Stage 2: Runner
# ------------------------------------------------------
FROM node:20-alpine AS runner

WORKDIR /app
ARG DATABASE_URL
ENV DATABASE_URL=${DATABASE_URL}
# Install runtime libs
RUN apk add --no-cache \
    cairo \
    jpeg \
    pango \
    giflib \
    librsvg \
    pixman \
    openssl

# Copy only what's needed
COPY --from=builder /app/package*.json ./
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/prisma ./prisma
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/WAProto ./WAProto
COPY --from=builder /app/WASignalGroup ./WASignalGroup


# Create runtime dirs
RUN mkdir -p logs uploads temp auth_sessions

EXPOSE 3001

# Healthcheck
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD node -e "require('http').get('http://localhost:3001/health', (res) => { process.exit(res.statusCode === 200 ? 0 : 1) })"

# Start the app
CMD ["node", "dist/app.js"]




