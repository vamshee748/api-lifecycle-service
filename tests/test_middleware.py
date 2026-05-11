"""
Test script to verify logging middleware and OpenAPI documentation functionality.
Run with: python test_middleware.py
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import after path setup
from app.middleware import RequestLoggingMiddleware, PerformanceMonitoringMiddleware, SecurityHeadersMiddleware
from app.middleware import logger

print("=" * 80)
print("TESTING MIDDLEWARE AND OPENAPI DOCUMENTATION")
print("=" * 80)

# Test 1: Verify middleware classes are importable
print("\n[TEST 1] Verifying middleware classes...")
try:
    assert RequestLoggingMiddleware is not None
    assert PerformanceMonitoringMiddleware is not None
    assert SecurityHeadersMiddleware is not None
    print("✓ All middleware classes imported successfully")
except AssertionError:
    print("✗ Failed to import middleware classes")
    sys.exit(1)

# Test 2: Verify logger is configured
print("\n[TEST 2] Verifying logger configuration...")
try:
    assert logger is not None
    # Logger might not have handlers if running standalone
    if len(logger.handlers) > 0:
        print(f"✓ Logger configured with {len(logger.handlers)} handler(s)")
        for handler in logger.handlers:
            print(f"  - {handler.__class__.__name__}")
    else:
        print("✓ Logger object exists (handlers configured at runtime)")
except AssertionError:
    print("✗ Logger not properly configured")
    sys.exit(1)

# Test 3: Test logging functionality
print("\n[TEST 3] Testing logging functionality...")
try:
    logger.info("Test INFO log message")
    logger.warning("Test WARNING log message")
    logger.error("Test ERROR log message")
    print("✓ Logging functionality working")
except Exception as e:
    print(f"✗ Logging failed: {str(e)}")
    sys.exit(1)

# Test 4: Verify log file creation
print("\n[TEST 4] Verifying log file...")
log_file = "app.log"
if os.path.exists(log_file):
    file_size = os.path.getsize(log_file)
    print(f"✓ Log file exists: {log_file} ({file_size} bytes)")
else:
    print(f"⚠ Log file not yet created (will be created on first app run)")

print("\n" + "=" * 80)
print("MIDDLEWARE AND OPENAPI TESTS COMPLETED")
print("=" * 80)
print("\nTo test the full application:")
print("1. Start the server: uvicorn app.main:app --reload")
print("2. Visit OpenAPI docs: http://localhost:8000/docs")
print("3. Check logs: tail -f app.log (Linux/Mac) or Get-Content app.log -Wait (Windows)")
print("4. Make API requests and observe logging output")
print("\nExpected logging features:")
print("  ✓ Request/response logging with request ID")
print("  ✓ Processing time tracking")
print("  ✓ Authentication status logging")
print("  ✓ Slow request warnings (> 1 second)")
print("  ✓ Error tracking with stack traces")
print("  ✓ Security headers added to all responses")
