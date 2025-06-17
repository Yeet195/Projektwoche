FROM node:18-alpine

WORKDIR /app

# Copy package files first for better caching
COPY package*.json ./

# Install ALL dependencies
RUN npm ci

# Copy source code
COPY . .

# Build the application
RUN npm run build

# Install simple HTTP server
RUN npm install -g serve

# Expose port
EXPOSE 3000

# Serve the static build directory
CMD ["serve", "-s", "build", "-l", "3000"]