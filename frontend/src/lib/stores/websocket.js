import { writable } from 'svelte/store';
import { io } from 'socket.io-client';

// Connection state
export const connected = writable(false);
export const connectionError = writable(null);

// Scan state
export const scanInProgress = writable(false);
export const scanProgress = writable({ phase: '', progress: 0, message: '' });
export const scanResults = writable(null);
export const scanHistory = writable([]);
export const statistics = writable({});

// WebSocket instance
let socket = null;

export function connectWebSocket(url = '/socket.io') {
    if (socket) {
        socket.disconnect();
    }

    socket = io(url, {
        autoConnect: true,
        reconnection: true,
        reconnectionDelay: 1000,
        reconnectionAttempts: 5,
        timeout: 20000,
    });

    socket.on('connect', () => {
        connected.set(true);
        connectionError.set(null);
        console.log('Connected to scan server');
    });

    socket.on('disconnect', () => {
        connected.set(false);
        scanInProgress.set(false);
        console.log('Disconnected from scan server');
    });

    socket.on('connect_error', (error) => {
        connected.set(false);
        connectionError.set(error.message);
        console.error('Connection error:', error);
    });

    socket.on('connected', (data) => {
        console.log('Server confirmed connection:', data);
    });

    socket.on('scan_started', (data) => {
        scanInProgress.set(true);
        scanProgress.set({ phase: 'starting', progress: 0, message: data.status });
        scanResults.set(null);
    });

    socket.on('scan_progress', (data) => {
        scanProgress.set(data);
    });

    socket.on('scan_complete', (data) => {
        scanInProgress.set(false);
        scanResults.set(data);
        scanProgress.set({ phase: 'complete', progress: 100, message: 'Scan completed' });
        // Refresh history
        requestScanHistory();
    });

    socket.on('scan_error', (data) => {
        scanInProgress.set(false);
        connectionError.set(data.error);
        console.error('Scan error:', data.error);
    });

    socket.on('scan_history', (data) => {
        scanHistory.set(data);
    });

    socket.on('statistics', (data) => {
        statistics.set(data);
    });

    return socket;
}

export function startScan(networkRange = null, notes = '') {
    if (socket && socket.connected) {
        socket.emit('start_scan', {
            network_range: networkRange,
            notes: notes
        });
    }
}

export function requestScanHistory() {
    if (socket && socket.connected) {
        socket.emit('get_scan_history');
    }
}

export function requestStatistics() {
    if (socket && socket.connected) {
        socket.emit('get_statistics');
    }
}

export function disconnectWebSocket() {
    if (socket) {
        socket.disconnect();
        socket = null;
    }
    connected.set(false);
}