<script>
    import { onMount, onDestroy } from 'svelte';
    import {
        connectWebSocket,
        disconnectWebSocket,
        startScan,
        requestScanHistory,
        requestStatistics,
        connected,
        connectionError,
        scanInProgress,
        scanProgress,
        scanResults,
        scanHistory,
        statistics
    } from '$lib/stores/websocket.js';

    let networkRange = '';
    let scanNotes = '';

    onMount(() => {
        connectWebSocket();
        // Request initial data
        setTimeout(() => {
            requestScanHistory();
            requestStatistics();
        }, 1000);
    });

    onDestroy(() => {
        disconnectWebSocket();
    });

    function handleStartScan() {
        startScan(networkRange || null, scanNotes);
    }

    function formatDate(dateString) {
        return new Date(dateString).toLocaleString();
    }

    function getProgressColor(progress) {
        if (progress < 30) return 'bg-red-500';
        if (progress < 70) return 'bg-yellow-500';
        return 'bg-green-500';
    }
</script>

<svelte:head>
    <title>Network Scanner Dashboard</title>
</svelte:head>

<div class="min-h-screen bg-gray-100 p-8">
    <div class="max-w-6xl mx-auto">
        <h1 class="text-4xl font-bold text-gray-800 mb-8">Network Scanner Dashboard</h1>

        <!-- Connection Status -->
        <div class="mb-6">
            {#if $connected}
                <div class="bg-green-100 border border-green-400 text-green-700 px-4 py-3 rounded">
                    Connected to scan server
                </div>
            {:else if $connectionError}
                <div class="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
                    Connection failed: {$connectionError}
                </div>
            {:else}
                <div class="bg-yellow-100 border border-yellow-400 text-yellow-700 px-4 py-3 rounded">
                    Connecting to scan server...
                </div>
            {/if}
        </div>

        <!-- Scan Control Panel -->
        <div class="bg-white rounded-lg shadow-md p-6 mb-6">
            <h2 class="text-2xl font-semibold mb-4">Start New Scan</h2>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                <div>
                    <label for="networkRange" class="block text-sm font-medium text-gray-700 mb-2">
                        Network Range (optional)
                    </label>
                    <input
                            id="networkRange"
                            type="text"
                            bind:value={networkRange}
                            placeholder="e.g., 192.168.1.0/24"
                            class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                            disabled={$scanInProgress}/>
                </div>
                <div>
                    <label for="scanNotes" class="block text-sm font-medium text-gray-700 mb-2">
                        Notes
                    </label>
                    <input
                            id="scanNotes"
                            type="text"
                            bind:value={scanNotes}
                            placeholder="Scan description"
                            class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                            disabled={$scanInProgress}/>
                </div>
            </div>

            <button
                    on:click={handleStartScan}
                    disabled={!$connected || $scanInProgress}
                    class="bg-blue-500 hover:bg-blue-600 disabled:bg-gray-400 text-white font-bold py-2 px-4 rounded">
                {$scanInProgress ? 'Scanning...' : 'Start Scan'}
            </button>
        </div>

        <!-- Scan Progress -->
        {#if $scanInProgress}
            <div class="bg-white rounded-lg shadow-md p-6 mb-6">
                <h2 class="text-2xl font-semibold mb-4">Scan Progress</h2>

                <div class="mb-4">
                    <div class="flex justify-between mb-2">
                        <span class="text-sm font-medium text-gray-700">
                            {$scanProgress.message}
                        </span>
                        <span class="text-sm font-medium text-gray-700">
                            {Math.round($scanProgress.progress || 0)}%
                        </span>
                    </div>
                    <div class="w-full bg-gray-200 rounded-full h-2.5">
                        <div
                                class="h-2.5 rounded-full transition-all duration-300 {getProgressColor($scanProgress.progress || 0)}"
                                style="width: {$scanProgress.progress || 0}%"
                        ></div>
                    </div>
                </div>

                {#if $scanProgress.current_ip}
                    <p class="text-sm text-gray-600">
                        Currently scanning: {$scanProgress.current_ip}
                        {#if $scanProgress.status}
                            - {$scanProgress.status}
                        {/if}
                        {#if $scanProgress.open_ports && $scanProgress.open_ports.length > 0}
                            - Open ports: {$scanProgress.open_ports.join(', ')}
                        {/if}
                    </p>
                {/if}
            </div>
        {/if}

        <!-- Latest Scan Results -->
        {#if $scanResults}
            <div class="bg-white rounded-lg shadow-md p-6 mb-6">
                <h2 class="text-2xl font-semibold mb-4">Latest Scan Results</h2>

                <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                    <div class="bg-blue-50 p-4 rounded">
                        <div class="text-2xl font-bold text-blue-600">{$scanResults.summary.total_hosts}</div>
                        <div class="text-sm text-gray-600">Total Hosts</div>
                    </div>
                    <div class="bg-green-50 p-4 rounded">
                        <div class="text-2xl font-bold text-green-600">{$scanResults.summary.online_hosts}</div>
                        <div class="text-sm text-gray-600">Online Hosts</div>
                    </div>
                    <div class="bg-yellow-50 p-4 rounded">
                        <div class="text-2xl font-bold text-yellow-600">{$scanResults.summary.hosts_with_ports}</div>
                        <div class="text-sm text-gray-600">Hosts with Open Ports</div>
                    </div>
                </div>

                <div class="mb-4">
                    <p class="text-sm text-gray-600">
                        Scan Duration: {$scanResults.duration.toFixed(2)}s |
                        Network: {$scanResults.network_range}
                    </p>
                </div>

                <!-- Online Hosts Table -->
                <div class="overflow-x-auto">
                    <table class="min-w-full table-auto">
                        <thead>
                        <tr class="bg-gray-50">
                            <th class="px-4 py-2 text-left">IP Address</th>
                            <th class="px-4 py-2 text-left">Status</th>
                            <th class="px-4 py-2 text-left">Open Ports</th>
                        </tr>
                        </thead>
                        <tbody>
                        {#each Object.entries($scanResults.results).filter(([ip, data]) => data.status === 'online') as [ip, data]}
                            <tr class="border-t">
                                <td class="px-4 py-2 font-mono">{ip}</td>
                                <td class="px-4 py-2">
                                        <span class="bg-green-100 text-green-800 px-2 py-1 rounded text-sm">
                                            {data.status}
                                        </span>
                                </td>
                                <td class="px-4 py-2">
                                    {#if data.ports.length > 0}
                                            <span class="bg-blue-100 text-blue-800 px-2 py-1 rounded text-sm">
                                                {data.ports.join(', ')}
                                            </span>
                                    {:else}
                                        <span class="text-gray-500">None</span>
                                    {/if}
                                </td>
                            </tr>
                        {/each}
                        </tbody>
                    </table>
                </div>
            </div>
        {/if}

        <!-- Statistics & History -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <!-- Statistics -->
            <div class="bg-white rounded-lg shadow-md p-6">
                <h3 class="text-xl font-semibold mb-4">Statistics</h3>
                {#if Object.keys($statistics).length > 0}
                    <div class="space-y-2">
                        <div class="flex justify-between">
                            <span>Total Scans:</span>
                            <span class="font-semibold">{$statistics.total_scans}</span>
                        </div>
                        <div class="flex justify-between">
                            <span>Unique IPs Scanned:</span>
                            <span class="font-semibold">{$statistics.unique_ips_scanned}</span>
                        </div>
                        <div class="flex justify-between">
                            <span>Last Scan:</span>
                            <span class="font-semibold">{$statistics.last_scan_date ? formatDate($statistics.last_scan_date) : 'Never'}</span>
                        </div>
                        <div class="flex justify-between">
                            <span>Avg Online Hosts:</span>
                            <span class="font-semibold">{$statistics.average_online_hosts}</span>
                        </div>
                    </div>
                {:else}
                    <p class="text-gray-500">No statistics available</p>
                {/if}
            </div>

            <!-- Scan History -->
            <div class="bg-white rounded-lg shadow-md p-6">
                <h3 class="text-xl font-semibold mb-4">Recent Scans</h3>
                {#if $scanHistory.length > 0}
                    <div class="space-y-3">
                        {#each $scanHistory.slice(0, 5) as scan}
                            <div class="border-l-4 border-blue-500 pl-4 py-2">
                                <div class="flex justify-between items-start">
                                    <div>
                                        <p class="font-semibold text-sm">{scan.network_range}</p>
                                        <p class="text-xs text-gray-600">{formatDate(scan.scan_date)}</p>
                                    </div>
                                    <div class="text-right">
                                        <p class="text-sm">{scan.online_hosts}/{scan.total_hosts} online</p>
                                        <p class="text-xs text-gray-600">{scan.scan_duration.toFixed(2)}s</p>
                                    </div>
                                </div>
                                {#if scan.notes}
                                    <p class="text-xs text-gray-500 mt-1">{scan.notes}</p>
                                {/if}
                            </div>
                        {/each}
                    </div>
                {:else}
                    <p class="text-gray-500">No scan history available</p>
                {/if}
            </div>
        </div>
    </div>
</div>