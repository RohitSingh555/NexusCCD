# Django Load Test Runner Script (PowerShell)
# 
# This script provides an easy way to run different load test scenarios on Windows
# 
# Usage:
#   .\run_load_test.ps1 [scenario] [api_url] [auth_token]
# 
# Scenarios:
#   - light: 1k records, 1 user, 2 minutes
#   - medium: 5k records, 3 users, 3 minutes  
#   - heavy: 10k records, 5 users, 5 minutes
#   - stress: 10k records, 10 users, 10 minutes (1M simulation)
#   - custom: Use environment variables for configuration

param(
    [string]$Scenario = "medium",
    [string]$ApiUrl = "http://localhost:8000/clients/upload/process/",
    [string]$AuthToken = "",
    [string]$OutputDir = "./load_test_results"
)

# Colors for output
$Red = "Red"
$Green = "Green"
$Yellow = "Yellow"
$Blue = "Blue"

Write-Host "🚀 Django Load Test Runner" -ForegroundColor $Blue
Write-Host "================================"
Write-Host "Scenario: $Scenario"
Write-Host "API URL: $ApiUrl"
Write-Host "Auth Token: $(if ($AuthToken) { 'Provided' } else { 'Not provided' })"
Write-Host "Output Directory: $OutputDir"
Write-Host ""

# Create output directory
if (!(Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

# Check if k6 is installed
try {
    $null = Get-Command k6 -ErrorAction Stop
} catch {
    Write-Host "❌ k6 is not installed. Please install k6 first:" -ForegroundColor $Red
    Write-Host "   Windows: choco install k6"
    Write-Host "   Or download from: https://k6.io/docs/getting-started/installation/"
    exit 1
}

# Check if the load test script exists
if (!(Test-Path "django_safe_load_test.js")) {
    Write-Host "❌ django_safe_load_test.js not found in current directory" -ForegroundColor $Red
    exit 1
}

# Function to run load test with specific configuration
function Run-LoadTest {
    param(
        [string]$ScenarioName,
        [int]$BatchSize,
        [int]$Concurrency,
        [int]$Duration,
        [string]$Description
    )
    
    Write-Host "🧪 Running $ScenarioName Test" -ForegroundColor $Yellow
    Write-Host "Description: $Description"
    Write-Host "Batch Size: $BatchSize records"
    Write-Host "Concurrency: $Concurrency users"
    Write-Host "Duration: $Duration minutes"
    Write-Host ""
    
    # Create a temporary config file
    $tempConfig = [System.IO.Path]::GetTempFileName()
    $configContent = @"
// Temporary configuration for $ScenarioName test
const CONFIG = {
    API_URL: '$ApiUrl',
    AUTH_TOKEN: '$AuthToken',
    BATCH_SIZE: $BatchSize,
    TOTAL_RECORDS: $($BatchSize * $Concurrency * $Duration / 60),
    CONCURRENCY: $Concurrency,
    STAGES: [
        { duration: '${Duration}m', target: $Concurrency, batchSize: $BatchSize, name: '$ScenarioName' }
    ],
    THRESHOLDS: {
        errorRate: 0.01,
        avgLatency: 10000,
        p95Latency: 20000,
        p99Latency: 30000
    }
};
"@
    
    Set-Content -Path $tempConfig -Value $configContent
    
    # Run the load test
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $outputFile = "$OutputDir/${ScenarioName}_${timestamp}"
    
    Write-Host "📊 Starting load test..." -ForegroundColor $Blue
    
    try {
        k6 run --config $tempConfig django_safe_load_test.js `
            --out "json=$outputFile.json" `
            --out "csv=$outputFile.csv" `
            --summary-export="$outputFile_summary.json"
        
        Write-Host "✅ $ScenarioName test completed" -ForegroundColor $Green
        Write-Host "Results saved to: $outputFile.*"
    } catch {
        Write-Host "❌ Load test failed: $($_.Exception.Message)" -ForegroundColor $Red
    } finally {
        # Clean up temp file
        Remove-Item $tempConfig -Force -ErrorAction SilentlyContinue
    }
    
    Write-Host ""
}

# Function to run verification test
function Run-Verification {
    Write-Host "🔍 Running verification test..." -ForegroundColor $Yellow
    
    if (!(Test-Path "verify_load_test_setup.py")) {
        Write-Host "❌ verify_load_test_setup.py not found" -ForegroundColor $Red
        return $false
    }
    
    $args = @("verify_load_test_setup.py", "--url", $ApiUrl)
    if ($AuthToken) {
        $args += @("--auth-token", $AuthToken)
    }
    
    try {
        python $args
        return $true
    } catch {
        Write-Host "❌ Verification failed: $($_.Exception.Message)" -ForegroundColor $Red
        return $false
    }
}

# Main execution
switch ($Scenario) {
    "light" {
        Run-LoadTest "light" 1000 1 2 "Light load test with 1k records"
    }
    "medium" {
        Run-LoadTest "medium" 5000 3 3 "Medium load test with 5k records"
    }
    "heavy" {
        Run-LoadTest "heavy" 10000 5 5 "Heavy load test with 10k records"
    }
    "stress" {
        Run-LoadTest "stress" 10000 10 10 "Stress test with 10k records (1M simulation)"
    }
    "verify" {
        Run-Verification
    }
    "all" {
        Write-Host "🔄 Running all test scenarios..." -ForegroundColor $Blue
        Run-LoadTest "light" 1000 1 2 "Light load test"
        Start-Sleep -Seconds 30  # Brief pause between tests
        Run-LoadTest "medium" 5000 3 3 "Medium load test"
        Start-Sleep -Seconds 30
        Run-LoadTest "heavy" 10000 5 5 "Heavy load test"
        Start-Sleep -Seconds 30
        Run-LoadTest "stress" 10000 10 10 "Stress test"
    }
    "custom" {
        # Use environment variables for custom configuration
        $batchSize = if ($env:BATCH_SIZE) { [int]$env:BATCH_SIZE } else { 10000 }
        $concurrency = if ($env:CONCURRENCY) { [int]$env:CONCURRENCY } else { 5 }
        $duration = if ($env:DURATION) { [int]$env:DURATION } else { 5 }
        Run-LoadTest "custom" $batchSize $concurrency $duration "Custom load test"
    }
    default {
        Write-Host "❌ Unknown scenario: $Scenario" -ForegroundColor $Red
        Write-Host ""
        Write-Host "Available scenarios:"
        Write-Host "  light    - 1k records, 1 user, 2 minutes"
        Write-Host "  medium   - 5k records, 3 users, 3 minutes"
        Write-Host "  heavy    - 10k records, 5 users, 5 minutes"
        Write-Host "  stress   - 10k records, 10 users, 10 minutes"
        Write-Host "  verify   - Verify Django setup"
        Write-Host "  all      - Run all scenarios"
        Write-Host "  custom   - Use environment variables (BATCH_SIZE, CONCURRENCY, DURATION)"
        Write-Host ""
        Write-Host "Examples:"
        Write-Host "  .\run_load_test.ps1 light"
        Write-Host "  .\run_load_test.ps1 heavy https://api.example.com/upload/"
        Write-Host "  .\run_load_test.ps1 custom"
        Write-Host "  `$env:BATCH_SIZE=5000; `$env:CONCURRENCY=3; `$env:DURATION=3; .\run_load_test.ps1 custom"
        exit 1
    }
}

Write-Host "🎉 Load testing completed!" -ForegroundColor $Green
Write-Host ""
Write-Host "📊 Results are available in: $OutputDir"
Write-Host ""
Write-Host "📈 To analyze results:"
Write-Host "  - JSON files: Detailed metrics and data"
Write-Host "  - CSV files: Time-series data for plotting"
Write-Host "  - Summary files: High-level performance metrics"
Write-Host ""
Write-Host "🔧 Next steps:"
Write-Host "  1. Review the performance metrics"
Write-Host "  2. Check if thresholds were met"
Write-Host "  3. Analyze any errors or warnings"
Write-Host "  4. Adjust your Django backend if needed"
Write-Host "  5. Run additional tests as required"
