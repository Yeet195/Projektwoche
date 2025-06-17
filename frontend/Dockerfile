FROM node:18-alpine

WORKDIR /app

# Copy package files first for better Docker layer caching
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy application code
COPY . .

# Build the application during Docker image build
RUN npm run build

# Verify build was created successfully
RUN ls -la build/ && echo "Build directory contents:" && find build/ -name "*.html" | head -5

# Install serve for production serving
RUN npm install -g serve

# Expose port
EXPOSE 3000

# Serve the static build directory
CMD ["serve", "-s", "build", "-l", "3000"]