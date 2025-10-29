# Django Load Testing Suite - Complete Package

## 📦 What You've Received

This package contains a comprehensive, production-safe load testing solution for your Django client upload API. Here's what's included:

### Core Files
1. **`django_safe_load_test.js`** - Main k6 load testing script
2. **`django_safe_load_test_artillery.yml`** - Alternative Artillery configuration
3. **`verify_load_test_setup.py`** - Django backend verification script
4. **`run_load_test.sh`** - Unix/Linux runner script
5. **`run_load_test.ps1`** - Windows PowerShell runner script

### Documentation
6. **`LOAD_TEST_README.md`** - Comprehensive usage guide
7. **`LOAD_TEST_SUMMARY.md`** - This overview document

## 🚀 Quick Start (3 Steps)

### Step 1: Verify Your Django Backend
```bash
# Test that your backend handles the X-Load-Test header
python verify_load_test_setup.py --url https://your-api-domain.com/clients/upload/process/
```

### Step 2: Configure the Load Test
Edit `django_safe_load_test.js` and update:
```javascript
const CONFIG = {
    API_URL: 'https://your-api-domain.com/clients/upload/process/',
    AUTH_TOKEN: 'your-jwt-token-here', // Optional
    // ... other settings
};
```

### Step 3: Run the Load Test
```bash
# Windows
.\run_load_test.ps1 medium

# Unix/Linux/macOS
./run_load_test.sh medium
```

## 🛡️ Safety Features

### Database Protection
- ✅ Uses `X-Load-Test: true` header to prevent data persistence
- ✅ Generates synthetic test data only
- ✅ No real client data is used or stored
- ✅ Safe to run against production

### Realistic Testing
- ✅ Generates 10,000+ unique client records per batch
- ✅ Includes all required fields from your Django model
- ✅ Uses realistic Canadian addresses, phone numbers, postal codes
- ✅ Varies data patterns to simulate real-world diversity

## 📊 Test Scenarios

| Scenario | Records | Users | Duration | Purpose |
|----------|---------|-------|----------|---------|
| **Light** | 1,000 | 1 | 2 min | Basic functionality test |
| **Medium** | 5,000 | 3 | 3 min | Normal load simulation |
| **Heavy** | 10,000 | 5 | 5 min | High load testing |
| **Stress** | 10,000 | 10 | 10 min | 1M record simulation |

## 🔧 Required Django Backend Changes

You need to modify your `clients/views.py` to handle the load test header:

```python
@csrf_exempt
@require_http_methods(["POST"])
def upload_clients(request):
    """Handle CSV/Excel file upload and process client data"""
    
    # Check for load test mode
    is_load_test = request.headers.get('X-Load-Test', '').lower() == 'true'
    
    if is_load_test:
        # Skip actual database writes in load test mode
        # Process the data but don't save to database
        processed_clients = process_upload_data(request)  # Your existing logic
        
        return JsonResponse({
            'success': True,
            'message': f'Load test mode: {len(processed_clients)} clients processed (no DB writes)',
            'load_test_mode': True,
            'processed_count': len(processed_clients)
        })
    
    # ... rest of your existing upload logic for normal operation ...
```

## 📈 Performance Metrics

The load test measures:
- **Latency**: Average, P95, P99 response times
- **Throughput**: Records processed per second
- **Error Rate**: Failed requests percentage
- **Memory Usage**: Approximate memory consumption
- **Success Rate**: Request success percentage

### Thresholds (Configurable)
- Error Rate: < 1%
- Average Latency: < 10s (for 10k batch)
- P95 Latency: < 20s
- P99 Latency: < 30s

## 🎯 Expected Results

### Good Performance
- ✅ Error rate < 1%
- ✅ Average latency < 10s for 10k records
- ✅ P95 latency < 20s
- ✅ Consistent throughput across test stages

### Warning Signs
- ⚠️ Error rate > 1%
- ⚠️ Latency increasing significantly with load
- ⚠️ Memory usage growing continuously
- ⚠️ Timeout errors

### Critical Issues
- ❌ Error rate > 5%
- ❌ Average latency > 30s
- ❌ Complete request failures
- ❌ Server crashes or unresponsiveness

## 🔍 Troubleshooting

### Common Issues

1. **"Connection Refused"**
   - Check your API_URL configuration
   - Verify Django server is running
   - Check CORS settings

2. **"Authentication Failed"**
   - Verify your AUTH_TOKEN is valid
   - Check token expiration
   - Ensure proper header format

3. **"High Error Rates"**
   - Check Django server logs
   - Verify X-Load-Test header handling
   - Consider reducing concurrency

4. **"Memory Issues"**
   - Reduce BATCH_SIZE
   - Increase server memory
   - Monitor server resources

### Debug Mode
Add this to your load test script for detailed logging:
```javascript
console.log(`📤 Uploading ${batchSize} records...`);
console.log(`📊 Response: ${response.status} - ${response.body.substring(0, 200)}...`);
```

## 📁 Output Files

After running tests, you'll find:
- `load_test_results/` - Directory containing all results
- `*.json` - Detailed metrics and data
- `*.csv` - Time-series data for plotting
- `*_summary.json` - High-level performance summary

## 🔄 Continuous Testing

### Automated Testing
```bash
# Run all scenarios
.\run_load_test.ps1 all

# Custom configuration
$env:BATCH_SIZE=5000; $env:CONCURRENCY=3; $env:DURATION=3; .\run_load_test.ps1 custom
```

### CI/CD Integration
Add to your deployment pipeline:
```yaml
- name: Load Test
  run: |
    python verify_load_test_setup.py --url ${{ secrets.API_URL }}
    .\run_load_test.ps1 medium
```

## 📞 Support & Customization

### Need Help?
1. Check the troubleshooting section
2. Review Django server logs
3. Test with smaller batch sizes first
4. Verify your API endpoint configuration

### Customization Options
- **Custom Fields**: Modify `generateClientData()` function
- **Test Patterns**: Adjust `CONFIG.STAGES` array
- **Thresholds**: Update `CONFIG.THRESHOLDS` values
- **Data Generation**: Customize the data generation logic

## 🎉 Success Criteria

Your load testing is successful when:
1. ✅ All test scenarios complete without critical errors
2. ✅ Performance metrics meet your thresholds
3. ✅ No data is persisted to production database
4. ✅ System remains stable under load
5. ✅ You have confidence in your API's performance

---

**Ready to test? Start with the verification script and work your way up to the full load test suite!** 🚀

Remember: This is a production-safe testing solution designed to give you confidence in your API's performance without risking your data.

