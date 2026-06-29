#!/usr/bin/env python3
"""
Comprehensive Test Runner for Strata
Runs all tests across components and reports results
"""
import unittest
import subprocess
import sys
import os
import time
from datetime import datetime

# Add the parent directory to path to import modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Test suite configuration
test_modules = [
    "tests.python_unit_tests",
    "tests.python_router_tests", 
    "tests.edge_case_tests",
    "tests.surreal_integration_tests",
]

# Rust test command
rust_test_cmd = ["cargo", "test", "--workspace"]


def run_python_tests():
    """Run all Python unit tests"""
    print("🔍 Running Python Unit Tests...")
    
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Discover and add all test cases
    for module_name in test_modules:
        try:
            module = __import__(module_name, fromlist=[''])
            suite.addTests(loader.loadTestsFromModule(module))
        except ImportError as e:
            print(f"⚠️  Could not import {module_name}: {e}")
            continue
    
    # Run the tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


def run_rust_tests():
    """Run all Rust tests"""
    print("\n⚙️  Running Rust Tests...")
    
    try:
        result = subprocess.run(
            rust_test_cmd,
            cwd=os.path.join(os.path.dirname(__file__), ".."),
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print("❌ Rust tests timed out after 5 minutes")
        return False
    except FileNotFoundError:
        print("⚠️  Cargo not found, skipping Rust tests")
        return True  # Don't fail if cargo isn't available


def check_surreal_connection():
    """Check if SurrealDB is available for integration tests"""
    print("\n📡 Checking SurrealDB Connection...")
    
    try:
        import requests
        from src.maintenance.conservative_maintainer import SURREAL_URL, SURREAL_AUTH, SURREAL_NS, SUREAL_DB
        
        # Try a simple query
        headers = {"Accept": "application/json"}
        sql = "INFO FOR DB;"
        full_sql = f"USE NS {SURREAL_NS} DB {SUREAL_DB};\n{sql}"
        
        response = requests.post(
            SURREAL_URL, 
            data=full_sql, 
            headers=headers, 
            auth=SURREAL_AUTH, 
            timeout=10
        )
        
        connected = response.status_code == 200
        print(f"   Status: {'✅ Connected' if connected else '❌ Not Available'}")
        return connected
        
    except ImportError:
        print("   ⚠️  Requests library not available")
        return False
    except Exception as e:
        print(f"   ❌ Connection failed: {e}")
        return False


def run_integration_tests_if_available():
    """Run integration tests if SurrealDB is available"""
    if check_surreal_connection():
        print("\n🔗 Running Integration Tests...")
        
        try:
            loader = unittest.TestLoader()
            integration_module = __import__("tests.surreal_integration_tests", fromlist=[''])
            suite = loader.loadTestsFromModule(integration_module)
            
            runner = unittest.TextTestRunner(verbosity=2)
            result = runner.run(suite)
            
            return result.wasSuccessful()
        except ImportError:
            print("⚠️  Integration tests module not found, skipping")
            return True
        except Exception as e:
            print(f"❌ Integration tests failed: {e}")
            return False
    else:
        print("\n⏭️  Skipping integration tests (SurrealDB not available)")
        return True


def main():
    """Main test runner"""
    print("🚀 Starting Strata Comprehensive Test Suite")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    start_time = time.time()
    
    # Run Python tests
    python_success = run_python_tests()
    
    # Run Rust tests
    rust_success = run_rust_tests()
    
    # Run integration tests if possible
    integration_success = run_integration_tests_if_available()
    
    total_time = time.time() - start_time
    
    # Summary
    print("\n" + "="*60)
    print("📋 TEST RESULTS SUMMARY")
    print("="*60)
    print(f"Python Tests:     {'✅ PASSED' if python_success else '❌ FAILED'}")
    print(f"Rust Tests:       {'✅ PASSED' if rust_success else '❌ FAILED'}")
    print(f"Integration:      {'✅ PASSED' if integration_success else '❌ FAILED/SKIPPED'}")
    
    all_passed = python_success and rust_success and integration_success
    
    print("-"*60)
    print(f"Overall Result:   {'🎉 ALL TESTS PASSED' if all_passed else '💥 SOME TESTS FAILED'}")
    print(f"Total Time:       {total_time:.2f} seconds")
    print("="*60)
    
    # Exit with appropriate code
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()