FROM node:18-alpine

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy source code
COPY . .

# Build the application
RUN npm run build

# Verify build exists
RUN ls -la build/

# Install serve to host the static files
RUN npm install -g serve

EXPOSE 3000

# Serve the built files
CMD ["serve", "-s", "build", "-l", "3000"]