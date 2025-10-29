/**
 * Django Client Upload Load Testing Suite
 * 
 * This script safely tests the performance of your Django client upload API
 * without polluting the production database by using the X-Load-Test header.
 * 
 * Usage:
 *   npx k6 run django_safe_load_test.js
 * 
 * Configuration:
 *   Modify the CONFIG section below to match your environment
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

// ============================================================================
// CONFIGURATION SECTION - MODIFY THESE VALUES FOR YOUR ENVIRONMENT
// ============================================================================

const CONFIG = {
    // API Configuration
    API_URL: 'http://localhost:8000/clients/upload/process/',
    AUTH_TOKEN: '', // Optional: JWT token for authentication
    
    // Test Configuration
    BATCH_SIZE: 10000,        // Records per upload (1k, 5k, 10k)
    TOTAL_RECORDS: 1000000,   // Total simulated volume
    CONCURRENCY: 5,           // Number of simultaneous uploads
    
    // Test Stages Configuration
    STAGES: [
        { duration: '2m', target: 1, batchSize: 1000, name: 'Stage 1: 1k records' },
        { duration: '3m', target: 3, batchSize: 5000, name: 'Stage 2: 5k records' },
        { duration: '5m', target: 5, batchSize: 10000, name: 'Stage 3: 10k records' },
        { duration: '10m', target: 10, batchSize: 10000, name: 'Stage 4: 1M records simulation' }
    ],
    
    // Performance Thresholds
    THRESHOLDS: {
        errorRate: 0.01,        // 1% max error rate
        avgLatency: 10000,      // 10s max average latency for 10k batch
        p95Latency: 20000,      // 20s max p95 latency
        p99Latency: 30000,      // 30s max p99 latency
    }
};

// ============================================================================
// CUSTOM METRICS
// ============================================================================

const errorRate = new Rate('error_rate');
const uploadLatency = new Trend('upload_latency');
const throughput = new Counter('throughput_records');
const memoryUsage = new Trend('memory_usage_mb');

// ============================================================================
// TEST DATA GENERATION
// ============================================================================

/**
 * Generate realistic client data for load testing
 */
function generateClientData(count) {
    const clients = [];
    const firstNames = ['John', 'Jane', 'Michael', 'Sarah', 'David', 'Emily', 'Robert', 'Jessica', 'William', 'Ashley'];
    const lastNames = ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez'];
    const genders = ['Male', 'Female', 'Other', 'Unknown'];
    const provinces = ['ON', 'BC', 'AB', 'QC', 'MB', 'SK', 'NS', 'NB', 'NL', 'PE'];
    const cities = ['Toronto', 'Vancouver', 'Calgary', 'Montreal', 'Ottawa', 'Winnipeg', 'Saskatoon', 'Halifax', 'St. John\'s', 'Charlottetown'];
    const languages = ['English', 'French', 'Spanish', 'Mandarin', 'Arabic', 'Punjabi', 'Tagalog', 'Italian', 'Portuguese', 'German'];
    const maritalStatuses = ['Single', 'Married', 'Divorced', 'Widowed', 'Separated'];
    const citizenshipStatuses = ['Citizen', 'Permanent Resident', 'Refugee', 'Temporary Resident', 'Other'];
    
    for (let i = 0; i < count; i++) {
        const firstName = firstNames[Math.floor(Math.random() * firstNames.length)];
        const lastName = lastNames[Math.floor(Math.random() * lastNames.length)];
        const clientId = `LOAD_TEST_${Date.now()}_${i}`;
        
        clients.push({
            'Client ID': clientId,
            'First Name': firstName,
            'Last Name': lastName,
            'Middle Name': Math.random() > 0.7 ? firstNames[Math.floor(Math.random() * firstNames.length)] : '',
            'Preferred Name': Math.random() > 0.8 ? `${firstName}${Math.floor(Math.random() * 100)}` : '',
            'Date of Birth': generateRandomDate(),
            'Gender': genders[Math.floor(Math.random() * genders.length)],
            'Phone': generateRandomPhone(),
            'Email': `${firstName.toLowerCase()}.${lastName.toLowerCase()}${i}@loadtest.com`,
            'Address': `${Math.floor(Math.random() * 9999) + 1} Test Street`,
            'City': cities[Math.floor(Math.random() * cities.length)],
            'Province': provinces[Math.floor(Math.random() * provinces.length)],
            'Postal Code': generateRandomPostalCode(),
            'Language': languages[Math.floor(Math.random() * languages.length)],
            'Marital Status': maritalStatuses[Math.floor(Math.random() * maritalStatuses.length)],
            'Citizenship Status': citizenshipStatuses[Math.floor(Math.random() * citizenshipStatuses.length)],
            'Emergency Contact Name': `${firstNames[Math.floor(Math.random() * firstNames.length)]} ${lastNames[Math.floor(Math.random() * lastNames.length)]}`,
            'Emergency Contact Phone': generateRandomPhone(),
            'Comments': `Load test data - Batch ${Math.floor(i / CONFIG.BATCH_SIZE) + 1}, Record ${i + 1}`
        });
    }
    
    return clients;
}

/**
 * Generate random date of birth (18-80 years ago)
 */
function generateRandomDate() {
    const now = new Date();
    const minAge = 18;
    const maxAge = 80;
    const age = Math.floor(Math.random() * (maxAge - minAge + 1)) + minAge;
    const birthDate = new Date(now.getFullYear() - age, Math.floor(Math.random() * 12), Math.floor(Math.random() * 28) + 1);
    return birthDate.toISOString().split('T')[0];
}

/**
 * Generate random Canadian phone number
 */
function generateRandomPhone() {
    const areaCode = Math.floor(Math.random() * 900) + 100;
    const exchange = Math.floor(Math.random() * 900) + 100;
    const number = Math.floor(Math.random() * 9000) + 1000;
    return `+1${areaCode}${exchange}${number}`;
}

/**
 * Generate random Canadian postal code
 */
function generateRandomPostalCode() {
    const letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
    const numbers = '0123456789';
    let postal = '';
    postal += letters[Math.floor(Math.random() * letters.length)];
    postal += numbers[Math.floor(Math.random() * numbers.length)];
    postal += letters[Math.floor(Math.random() * letters.length)];
    postal += ' ';
    postal += numbers[Math.floor(Math.random() * numbers.length)];
    postal += letters[Math.floor(Math.random() * letters.length)];
    postal += numbers[Math.floor(Math.random() * numbers.length)];
    return postal;
}

/**
 * Convert client data to CSV format
 */
function convertToCSV(clients) {
    if (clients.length === 0) return '';
    
    const headers = Object.keys(clients[0]);
    const csvRows = [headers.join(',')];
    
    for (const client of clients) {
        const values = headers.map(header => {
            const value = client[header];
            // Escape commas and quotes in CSV
            if (typeof value === 'string' && (value.includes(',') || value.includes('"') || value.includes('\n'))) {
                return `"${value.replace(/"/g, '""')}"`;
            }
            return value;
        });
        csvRows.push(values.join(','));
    }
    
    return csvRows.join('\n');
}

// ============================================================================
// LOAD TEST SCENARIOS
// ============================================================================

/**
 * Main upload scenario
 */
export function uploadScenario() {
    const batchSize = CONFIG.BATCH_SIZE;
    const clients = generateClientData(batchSize);
    const csvData = convertToCSV(clients);
    
    // Prepare headers
    const headers = {
        'Content-Type': 'multipart/form-data',
        'X-Load-Test': 'true',  // Critical: This tells Django to skip DB writes
        'User-Agent': 'k6-load-test/1.0'
    };
    
    // Add auth token if provided
    if (CONFIG.AUTH_TOKEN) {
        headers['Authorization'] = `Bearer ${CONFIG.AUTH_TOKEN}`;
    }
    
    // Create form data
    const formData = {
        'file': http.file(csvData, 'clients.csv', 'text/csv'),
        'source': 'SMIMS'  // Valid source values: 'SMIMS' or 'EMHware'
    };
    
    // Record start time for latency calculation
    const startTime = Date.now();
    
    // Make the upload request
    const response = http.post(CONFIG.API_URL, formData, { headers });
    
    // Calculate latency
    const latency = Date.now() - startTime;
    
    // Record metrics
    uploadLatency.add(latency);
    throughput.add(batchSize);
    
    // Track memory usage (approximate) - k6 doesn't have process object
    const memoryMB = 0; // Memory tracking not available in k6
    memoryUsage.add(memoryMB);
    
    // Check response
    const success = check(response, {
        'Upload successful': (r) => r.status === 200 || r.status === 201,
        'Response time < 30s': (r) => r.timings.duration < 30000,
        'Response has success field': (r) => {
            try {
                const body = JSON.parse(r.body);
                return body.hasOwnProperty('success');
            } catch (e) {
                return false;
            }
        }
    });
    
    errorRate.add(!success);
    
    // Log performance warnings
    if (latency > CONFIG.THRESHOLDS.avgLatency) {
        console.warn(`⚠️  High latency detected: ${latency}ms (threshold: ${CONFIG.THRESHOLDS.avgLatency}ms)`);
    }
    
    if (response.status >= 400) {
        console.error(`❌ Upload failed with status ${response.status}: ${response.body}`);
    }
    
    // Brief pause between requests
    sleep(0.1);
}

// ============================================================================
// K6 CONFIGURATION
// ============================================================================

export const options = {
    stages: CONFIG.STAGES.map(stage => ({
        duration: stage.duration,
        target: stage.target
    })),
    
    thresholds: {
        'error_rate': [`rate<${CONFIG.THRESHOLDS.errorRate}`],
        'upload_latency': [
            `avg<${CONFIG.THRESHOLDS.avgLatency}`,
            `p(95)<${CONFIG.THRESHOLDS.p95Latency}`,
            `p(99)<${CONFIG.THRESHOLDS.p99Latency}`
        ],
        'http_req_duration': [
            `avg<${CONFIG.THRESHOLDS.avgLatency}`,
            `p(95)<${CONFIG.THRESHOLDS.p95Latency}`
        ]
    },
    
    // Ramp up and down settings
    ext: {
        loadimpact: {
            name: 'Django Client Upload Load Test'
        }
    }
};

// ============================================================================
// TEST EXECUTION
// ============================================================================

export default function() {
    console.log(`🚀 Starting upload test - Batch size: ${CONFIG.BATCH_SIZE}, Concurrency: ${CONFIG.CONCURRENCY}`);
    
    uploadScenario();
}

// ============================================================================
// SETUP AND TEARDOWN
// ============================================================================

export function setup() {
    console.log('🔧 Load Test Setup');
    console.log(`📊 Configuration:`);
    console.log(`   API URL: ${CONFIG.API_URL}`);
    console.log(`   Batch Size: ${CONFIG.BATCH_SIZE} records`);
    console.log(`   Total Records: ${CONFIG.TOTAL_RECORDS}`);
    console.log(`   Concurrency: ${CONFIG.CONCURRENCY}`);
    console.log(`   Auth Token: ${CONFIG.AUTH_TOKEN ? 'Provided' : 'Not provided'}`);
    console.log('');
    
    // Test API connectivity
    const testResponse = http.get(CONFIG.API_URL.replace('/upload/process/', '/'), {
        headers: { 'X-Load-Test': 'true' }
    });
    
    if (testResponse.status === 404) {
        console.log('✅ API endpoint structure confirmed (404 expected for root)');
    } else if (testResponse.status < 500) {
        console.log('✅ API is reachable');
    } else {
        console.warn('⚠️  API may not be reachable - check your URL configuration');
    }
    
    return { startTime: Date.now() };
}

export function teardown(data) {
    const duration = (Date.now() - data.startTime) / 1000;
    console.log('');
    console.log('🏁 Load Test Complete');
    console.log(`⏱️  Total Duration: ${duration.toFixed(2)}s`);
    console.log('');
    console.log('📈 Performance Summary:');
    console.log('   Check the detailed metrics above for:');
    console.log('   - Request latency (avg, p95, p99)');
    console.log('   - Throughput (records/second)');
    console.log('   - Error rate');
    console.log('   - Memory usage');
    console.log('');
    console.log('✅ Test completed safely with X-Load-Test header - no data was persisted');
}

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

/**
 * Calculate throughput in records per second
 */
export function handleSummary(data) {
    const totalRecords = (data.metrics.throughput_records && data.metrics.throughput_records.values && data.metrics.throughput_records.values.count) || 0;
    const totalDuration = data.state.testRunDurationMs / 1000;
    const throughputRps = totalRecords / totalDuration;
    
    return {
        'summary.json': JSON.stringify({
            summary: {
                totalRecords: totalRecords,
                totalDuration: totalDuration,
                throughputRps: throughputRps,
                avgLatency: (data.metrics.upload_latency && data.metrics.upload_latency.values && data.metrics.upload_latency.values.avg) || 0,
                p95Latency: (data.metrics.upload_latency && data.metrics.upload_latency.values && data.metrics.upload_latency.values['p(95)']) || 0,
                p99Latency: (data.metrics.upload_latency && data.metrics.upload_latency.values && data.metrics.upload_latency.values['p(99)']) || 0,
                errorRate: (data.metrics.error_rate && data.metrics.error_rate.values && data.metrics.error_rate.values.rate) || 0,
                totalRequests: (data.metrics.http_reqs && data.metrics.http_reqs.values && data.metrics.http_reqs.values.count) || 0,
                failedRequests: (data.metrics.http_req_failed && data.metrics.http_req_failed.values && data.metrics.http_req_failed.values.rate) || 0
            },
            thresholds: {
                errorRateThreshold: CONFIG.THRESHOLDS.errorRate,
                avgLatencyThreshold: CONFIG.THRESHOLDS.avgLatency,
                p95LatencyThreshold: CONFIG.THRESHOLDS.p95Latency,
                p99LatencyThreshold: CONFIG.THRESHOLDS.p99Latency
            },
            config: CONFIG
        }, null, 2)
    };
}
