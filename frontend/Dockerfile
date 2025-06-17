FROM node:18-alpine

WORKDIR /app

# Copy package files first for better caching
COPY package*.json ./

# Install all dependencies (including dev dependencies)
RUN npm ci

# Copy source code
COPY . .

# Build the application
RUN npm run build

# Install serve for production serving
RUN npm install -g serve

# Expose port
EXPOSE 3000

# Serve the built application
CMD ["serve", "-s", "build", "-l", "3000"]