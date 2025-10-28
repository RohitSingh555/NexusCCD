/**
 * Simple Django Load Test - Safe Version
 * 
 * This is a simplified version with smaller batch sizes for safer testing
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

// Configuration
const CONFIG = {
    API_URL: 'http://localhost:8000/clients/upload/process/',
    BATCH_SIZE: 100,  // Small batch for safety
    CONCURRENCY: 1,   // Single user
    DURATION: '30s'   // 30 seconds
};

// Metrics
const errorRate = new Rate('error_rate');
const uploadLatency = new Trend('upload_latency');
const throughput = new Counter('throughput_records');

// Generate test data
function generateClientData(count) {
    const clients = [];
    const firstNames = ['John', 'Jane', 'Michael', 'Sarah', 'David'];
    const lastNames = ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones'];
    const genders = ['Male', 'Female', 'Other', 'Unknown'];
    
    for (let i = 0; i < count; i++) {
        const firstName = firstNames[Math.floor(Math.random() * firstNames.length)];
        const lastName = lastNames[Math.floor(Math.random() * lastNames.length)];
        const clientId = `LOAD_TEST_${Date.now()}_${i}`;
        
        clients.push({
            'Client ID': clientId,
            'First Name': firstName,
            'Last Name': lastName,
            'Date of Birth': '1990-01-01',
            'Gender': genders[Math.floor(Math.random() * genders.length)],
            'Phone': `+1555${String(Math.floor(Math.random() * 10000000)).padStart(7, '0')}`,
            'Email': `${firstName.toLowerCase()}.${lastName.toLowerCase()}${i}@loadtest.com`,
            'Address': `${Math.floor(Math.random() * 9999) + 1} Test Street`,
            'City': 'Test City',
            'Province': 'ON',
            'Postal Code': 'K1A 0A1',
            'Comments': `Load test data - Record ${i + 1}`
        });
    }
    
    return clients;
}

// Convert to CSV
function convertToCSV(clients) {
    if (clients.length === 0) return '';
    
    const headers = Object.keys(clients[0]);
    const csvRows = [headers.join(',')];
    
    for (const client of clients) {
        const values = headers.map(header => {
            const value = client[header];
            if (typeof value === 'string' && (value.includes(',') || value.includes('"') || value.includes('\n'))) {
                return `"${value.replace(/"/g, '""')}"`;
            }
            return value;
        });
        csvRows.push(values.join(','));
    }
    
    return csvRows.join('\n');
}

// Main test function
export default function() {
    console.log(`🚀 Starting upload test - Batch size: ${CONFIG.BATCH_SIZE}`);
    
    // Generate test data
    const clients = generateClientData(CONFIG.BATCH_SIZE);
    const csvData = convertToCSV(clients);
    
    // Prepare request
    const headers = {
        'X-Load-Test': 'true',
        'User-Agent': 'k6-load-test/1.0'
    };
    
    const formData = {
        'file': http.file(csvData, 'clients.csv', 'text/csv'),
        'source': 'SMIMS'
    };
    
    // Record start time
    const startTime = Date.now();
    
    // Make request
    const response = http.post(CONFIG.API_URL, formData, { headers });
    
    // Calculate latency
    const latency = Date.now() - startTime;
    
    // Record metrics
    uploadLatency.add(latency);
    throughput.add(CONFIG.BATCH_SIZE);
    
    // Check response
    const success = check(response, {
        'Upload successful': (r) => r.status === 200 || r.status === 201,
        'Response time < 10s': (r) => r.timings.duration < 10000,
        'Has success field': (r) => {
            try {
                const body = JSON.parse(r.body);
                return body.hasOwnProperty('success');
            } catch (e) {
                return false;
            }
        }
    });
    
    errorRate.add(!success);
    
    // Log results
    if (success) {
        console.log(`✅ Upload successful - ${latency}ms`);
    } else {
        console.log(`❌ Upload failed - Status: ${response.status}, Latency: ${latency}ms`);
        console.log(`Response: ${response.body.substring(0, 200)}...`);
    }
    
    // Brief pause
    sleep(1);
}

// Test configuration
export const options = {
    vus: CONFIG.CONCURRENCY,
    duration: CONFIG.DURATION,
    thresholds: {
        'error_rate': ['rate<0.1'],  // Less than 10% error rate
        'upload_latency': ['avg<5000', 'p(95)<10000']  // Average < 5s, P95 < 10s
    }
};
