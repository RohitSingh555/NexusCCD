# Django Client Upload Load Testing Suite

A comprehensive, safe load testing solution for your Django client upload API that simulates high-volume data uploads without polluting your production database.

## 🚀 Quick Start

### Prerequisites

- Node.js (v14 or higher)
- k6 (for JavaScript-based testing)
- Artillery (alternative option)

### Installation

```bash
# Install k6 (recommended)
# Windows (using Chocolatey)
choco install k6

# macOS (using Homebrew)
brew install k6

# Linux (using package manager)
sudo apt-get install k6

# Or download from: https://k6.io/docs/getting-started/installation/

# Install Artillery (alternative)
npm install -g artillery
```

### Basic Usage

1. **Configure your API endpoint** in `django_safe_load_test.js`:
   ```javascript
   const CONFIG = {
       API_URL: 'https://your-api-domain.com/clients/upload/process/',
       AUTH_TOKEN: 'your-jwt-token-here', // Optional
       // ... other settings
   };
   ```

2. **Run the load test**:
   ```bash
   npx k6 run django_safe_load_test.js
   ```

3. **View results**:
   The test will output real-time metrics and generate a `summary.json` file with detailed results.

## 🔧 Configuration Options

### API Configuration
- `API_URL`: Your Django upload endpoint URL
- `AUTH_TOKEN`: Optional JWT authentication token
- `BATCH_SIZE`: Records per upload (1,000 / 5,000 / 10,000)
- `TOTAL_RECORDS`: Total simulated volume (default: 1,000,000)
- `CONCURRENCY`: Number of simultaneous uploads (1-20)

### Test Stages
The test runs in 4 progressive stages:
1. **Stage 1**: 1k records, 1 concurrent user, 2 minutes
2. **Stage 2**: 5k records, 3 concurrent users, 3 minutes  
3. **Stage 3**: 10k records, 5 concurrent users, 5 minutes
4. **Stage 4**: 10k records, 10 concurrent users, 10 minutes (1M simulation)

### Performance Thresholds
- **Error Rate**: < 1%
- **Average Latency**: < 10s (for 10k batch)
- **P95 Latency**: < 20s
- **P99 Latency**: < 30s

## 🛡️ Safety Features

### Database Protection
- Uses `X-Load-Test: true` header to prevent data persistence
- Generates synthetic test data only
- No real client data is used or stored

### Realistic Test Data
- Generates 10,000+ unique client records per batch
- Includes all required fields: client_id, first_name, last_name, phone, email, etc.
- Uses realistic Canadian addresses, phone numbers, and postal codes
- Varies data patterns to simulate real-world diversity

## 📊 Metrics & Reporting

### Real-time Metrics
- Request latency (average, p95, p99)
- Throughput (records/second)
- Error rate and failed requests
- Memory usage tracking
- Request success/failure rates

### Output Files
- `summary.json`: Detailed performance summary
- Console output: Real-time progress and warnings
- k6 built-in reporting: HTML and JSON reports

## 🎯 Test Scenarios

### Scenario 1: Light Load (1k records)
```bash
# Modify CONFIG.BATCH_SIZE = 1000
npx k6 run django_safe_load_test.js
```

### Scenario 2: Medium Load (5k records)
```bash
# Modify CONFIG.BATCH_SIZE = 5000
npx k6 run django_safe_load_test.js
```

### Scenario 3: Heavy Load (10k records)
```bash
# Modify CONFIG.BATCH_SIZE = 10000
npx k6 run django_safe_load_test.js
```

### Scenario 4: Stress Test (1M records simulation)
```bash
# Modify CONFIG.TOTAL_RECORDS = 1000000
npx k6 run django_safe_load_test.js
```

## 🔍 Troubleshooting

### Common Issues

1. **Connection Refused**
   - Verify your API_URL is correct
   - Check if your Django server is running
   - Ensure CORS is configured for your domain

2. **Authentication Errors**
   - Verify your AUTH_TOKEN is valid
   - Check token expiration
   - Ensure proper Authorization header format

3. **High Error Rates**
   - Check server logs for detailed error messages
   - Verify your Django upload endpoint handles the X-Load-Test header
   - Consider reducing concurrency or batch size

4. **Memory Issues**
   - Reduce BATCH_SIZE for large datasets
   - Increase server memory allocation
   - Monitor server resource usage

### Debug Mode
Add debug logging to see detailed request/response information:

```javascript
// In django_safe_load_test.js, add this to the uploadScenario function:
console.log(`📤 Uploading ${batchSize} records...`);
console.log(`📊 Response: ${response.status} - ${response.body.substring(0, 200)}...`);
```

## 📈 Performance Analysis

### Key Metrics to Monitor

1. **Latency Trends**
   - How does response time change with load?
   - Are there any latency spikes?
   - Does p95/p99 latency stay within thresholds?

2. **Throughput Analysis**
   - Records processed per second
   - Peak throughput capacity
   - Throughput degradation under load

3. **Error Patterns**
   - Error rate by stage
   - Common error types
   - Recovery patterns

4. **Resource Utilization**
   - Memory usage trends
   - CPU impact on server
   - Database connection usage

### Sample Results Interpretation

```json
{
  "summary": {
    "totalRecords": 1000000,
    "totalDuration": 600,
    "throughputRps": 1666.67,
    "avgLatency": 8500,
    "p95Latency": 15000,
    "errorRate": 0.002
  }
}
```

**Interpretation:**
- ✅ **Throughput**: 1,667 records/second is excellent
- ✅ **Error Rate**: 0.2% is well below 1% threshold
- ⚠️ **Average Latency**: 8.5s is close to 10s threshold
- ✅ **P95 Latency**: 15s is well below 20s threshold

## 🔄 Alternative: Artillery Version

For users who prefer Artillery over k6, use `django_safe_load_test_artillery.yml`:

```bash
# Install Artillery
npm install -g artillery

# Run Artillery test
artillery run django_safe_load_test_artillery.yml
```

## 🚨 Important Notes

1. **Production Safety**: Always use the `X-Load-Test: true` header
2. **Server Resources**: Monitor your server during testing
3. **Network Impact**: Consider bandwidth limitations
4. **Database Load**: Even with test mode, queries may still execute
5. **Rate Limiting**: Check if your API has rate limits

## 📞 Support

If you encounter issues or need customizations:

1. Check the troubleshooting section above
2. Review your Django server logs
3. Verify your API endpoint configuration
4. Test with smaller batch sizes first

## 🔧 Customization

### Adding Custom Fields
Modify the `generateClientData()` function to include additional client fields:

```javascript
clients.push({
    'Client ID': clientId,
    'First Name': firstName,
    'Last Name': lastName,
    // Add your custom fields here
    'Custom Field': 'Custom Value',
    // ... existing fields
});
```

### Adjusting Test Patterns
Modify the `CONFIG.STAGES` array to create custom test patterns:

```javascript
STAGES: [
    { duration: '1m', target: 1, batchSize: 1000, name: 'Warm-up' },
    { duration: '5m', target: 10, batchSize: 5000, name: 'Ramp-up' },
    { duration: '10m', target: 20, batchSize: 10000, name: 'Sustained Load' },
    { duration: '2m', target: 0, batchSize: 10000, name: 'Cool-down' }
]
```

---

**Happy Load Testing! 🚀**

Remember: This test suite is designed to be safe for production use, but always monitor your server resources and have a rollback plan ready.

