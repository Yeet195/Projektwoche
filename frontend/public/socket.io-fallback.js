// Fallback Socket.IO client - minimal implementation
console.warn('Using fallback Socket.IO implementation');

function createFallbackSocket() {
    return {
        connected: false,
        on: () => {},
        emit: () => {},
        connect: () => {},
        disconnect: () => {}
    };
}

if (typeof io === 'undefined') {
    window.io = () => createFallbackSocket();
}