#!/bin/bash

# Django Load Test Runner Script
# 
# This script provides an easy way to run different load test scenarios
# 
# Usage:
#   ./run_load_test.sh [scenario] [api_url] [auth_token]
# 
# Scenarios:
#   - light: 1k records, 1 user, 2 minutes
#   - medium: 5k records, 3 users, 3 minutes  
#   - heavy: 10k records, 5 users, 5 minutes
#   - stress: 10k records, 10 users, 10 minutes (1M simulation)
#   - custom: Use environment variables for configuration

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
SCENARIO=${1:-"medium"}
API_URL=${2:-"https://your-api-domain.com/clients/upload/process/"}
AUTH_TOKEN=${3:-""}
OUTPUT_DIR="./load_test_results"

# Create output directory
mkdir -p "$OUTPUT_DIR"

echo -e "${BLUE}🚀 Django Load Test Runner${NC}"
echo "================================"
echo "Scenario: $SCENARIO"
echo "API URL: $API_URL"
echo "Auth Token: ${AUTH_TOKEN:+Provided}"
echo "Output Directory: $OUTPUT_DIR"
echo ""

# Check if k6 is installed
if ! command -v k6 &> /dev/null; then
    echo -e "${RED}❌ k6 is not installed. Please install k6 first:${NC}"
    echo "   Windows: choco install k6"
    echo "   macOS: brew install k6"
    echo "   Linux: sudo apt-get install k6"
    echo "   Or download from: https://k6.io/docs/getting-started/installation/"
    exit 1
fi

# Check if the load test script exists
if [ ! -f "django_safe_load_test.js" ]; then
    echo -e "${RED}❌ django_safe_load_test.js not found in current directory${NC}"
    exit 1
fi

# Function to run load test with specific configuration
run_load_test() {
    local scenario_name=$1
    local batch_size=$2
    local concurrency=$3
    local duration=$4
    local description=$5
    
    echo -e "${YELLOW}🧪 Running $scenario_name Test${NC}"
    echo "Description: $description"
    echo "Batch Size: $batch_size records"
    echo "Concurrency: $concurrency users"
    echo "Duration: $duration"
    echo ""
    
    # Create a temporary config file
    local temp_config=$(mktemp)
    cat > "$temp_config" << EOF
// Temporary configuration for $scenario_name test
const CONFIG = {
    API_URL: '$API_URL',
    AUTH_TOKEN: '$AUTH_TOKEN',
    BATCH_SIZE: $batch_size,
    TOTAL_RECORDS: $((batch_size * concurrency * duration / 60)),
    CONCURRENCY: $concurrency,
    STAGES: [
        { duration: '${duration}m', target: $concurrency, batchSize: $batch_size, name: '$scenario_name' }
    ],
    THRESHOLDS: {
        errorRate: 0.01,
        avgLatency: 10000,
        p95Latency: 20000,
        p99Latency: 30000
    }
};
EOF
    
    # Run the load test
    local timestamp=$(date +"%Y%m%d_%H%M%S")
    local output_file="$OUTPUT_DIR/${scenario_name}_${timestamp}"
    
    echo -e "${BLUE}📊 Starting load test...${NC}"
    k6 run --config "$temp_config" django_safe_load_test.js \
        --out json="$output_file.json" \
        --out csv="$output_file.csv" \
        --summary-export="$output_file_summary.json"
    
    # Clean up temp file
    rm "$temp_config"
    
    echo -e "${GREEN}✅ $scenario_name test completed${NC}"
    echo "Results saved to: $output_file.*"
    echo ""
}

# Function to run verification test
run_verification() {
    echo -e "${YELLOW}🔍 Running verification test...${NC}"
    
    if [ ! -f "verify_load_test_setup.py" ]; then
        echo -e "${RED}❌ verify_load_test_setup.py not found${NC}"
        return 1
    fi
    
    python3 verify_load_test_setup.py --url "$API_URL" ${AUTH_TOKEN:+--auth-token "$AUTH_TOKEN"}
}

# Main execution
case $SCENARIO in
    "light")
        run_load_test "light" 1000 1 2 "Light load test with 1k records"
        ;;
    "medium")
        run_load_test "medium" 5000 3 3 "Medium load test with 5k records"
        ;;
    "heavy")
        run_load_test "heavy" 10000 5 5 "Heavy load test with 10k records"
        ;;
    "stress")
        run_load_test "stress" 10000 10 10 "Stress test with 10k records (1M simulation)"
        ;;
    "verify")
        run_verification
        ;;
    "all")
        echo -e "${BLUE}🔄 Running all test scenarios...${NC}"
        run_load_test "light" 1000 1 2 "Light load test"
        sleep 30  # Brief pause between tests
        run_load_test "medium" 5000 3 3 "Medium load test"
        sleep 30
        run_load_test "heavy" 10000 5 5 "Heavy load test"
        sleep 30
        run_load_test "stress" 10000 10 10 "Stress test"
        ;;
    "custom")
        # Use environment variables for custom configuration
        BATCH_SIZE=${BATCH_SIZE:-10000}
        CONCURRENCY=${CONCURRENCY:-5}
        DURATION=${DURATION:-5}
        run_load_test "custom" "$BATCH_SIZE" "$CONCURRENCY" "$DURATION" "Custom load test"
        ;;
    *)
        echo -e "${RED}❌ Unknown scenario: $SCENARIO${NC}"
        echo ""
        echo "Available scenarios:"
        echo "  light    - 1k records, 1 user, 2 minutes"
        echo "  medium   - 5k records, 3 users, 3 minutes"
        echo "  heavy    - 10k records, 5 users, 5 minutes"
        echo "  stress   - 10k records, 10 users, 10 minutes"
        echo "  verify   - Verify Django setup"
        echo "  all      - Run all scenarios"
        echo "  custom   - Use environment variables (BATCH_SIZE, CONCURRENCY, DURATION)"
        echo ""
        echo "Examples:"
        echo "  ./run_load_test.sh light"
        echo "  ./run_load_test.sh heavy https://api.example.com/upload/"
        echo "  ./run_load_test.sh custom"
        echo "  BATCH_SIZE=5000 CONCURRENCY=3 DURATION=3 ./run_load_test.sh custom"
        exit 1
        ;;
esac

echo -e "${GREEN}🎉 Load testing completed!${NC}"
echo ""
echo "📊 Results are available in: $OUTPUT_DIR"
echo ""
echo "📈 To analyze results:"
echo "  - JSON files: Detailed metrics and data"
echo "  - CSV files: Time-series data for plotting"
echo "  - Summary files: High-level performance metrics"
echo ""
echo "🔧 Next steps:"
echo "  1. Review the performance metrics"
echo "  2. Check if thresholds were met"
echo "  3. Analyze any errors or warnings"
echo "  4. Adjust your Django backend if needed"
echo "  5. Run additional tests as required"

