#!/usr/bin/env python3
"""
Performance testing script for mesh-scout cache implementation
"""

import requests
import time
import sys
from datetime import datetime

# Configuration
BASE_URL = "http://localhost:5000"
ENDPOINTS = [
    ("/api/devices", "Devices API"),
    ("/api/stats", "Stats API"),
    ("/api/highscore/all?limit=20", "Highscore API"),
    ("/api/coverage?limit=1000", "Coverage API (1000 hexagons)"),
]

def test_endpoint(url, name, iterations=3):
    """Test endpoint performance"""
    print(f"\n{'='*60}")
    print(f"Testing: {name}")
    print(f"URL: {url}")
    print(f"{'='*60}")
    
    times = []
    
    for i in range(iterations):
        start = time.time()
        try:
            response = requests.get(url, timeout=30)
            end = time.time()
            duration = end - start
            
            if response.status_code == 200:
                times.append(duration)
                print(f"  Request {i+1}: {duration:.3f}s - ✅ Status: {response.status_code}")
                
                # Show response size
                try:
                    data = response.json()
                    if 'total' in data:
                        print(f"    └─ Total items: {data['total']}")
                except (ValueError, KeyError):
                    pass
            else:
                print(f"  Request {i+1}: ❌ Status: {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            print(f"  Request {i+1}: ❌ Error: {e}")
            return None
        
        # Small delay between requests
        if i < iterations - 1:
            time.sleep(0.5)
    
    if times:
        avg_time = sum(times) / len(times)
        first_time = times[0]
        cached_time = sum(times[1:]) / (len(times) - 1) if len(times) > 1 else times[0]
        
        print(f"\n  📊 Results:")
        print(f"    First request (cold cache): {first_time:.3f}s")
        if len(times) > 1:
            print(f"    Cached requests (avg):      {cached_time:.3f}s")
            speedup = first_time / cached_time if cached_time > 0 else 0
            print(f"    Speedup:                    {speedup:.1f}x faster")
            
            if speedup < 2:
                print(f"    ⚠️  WARNING: Cache may not be working! Expected >2x speedup")
        
        return times
    
    return None


def check_cache_status():
    """Check if cache is configured"""
    print("\n" + "="*60)
    print("Cache Status Check")
    print("="*60)
    
    try:
        response = requests.get(f"{BASE_URL}/api/cache/info", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print("✅ Cache endpoint available")
            print(f"\nCache Configuration:")
            print(f"  Type: {data.get('cache_type', 'Unknown')}")
            print(f"  Default timeout: {data.get('default_timeout', 'Unknown')}s")
            
            if 'endpoints_cached' in data:
                print(f"\n  Cached endpoints:")
                for endpoint, timeout in data['endpoints_cached'].items():
                    print(f"    • {endpoint}: {timeout}")
            
            return True
        else:
            print(f"❌ Cache endpoint returned: {response.status_code}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Cannot connect to cache endpoint: {e}")
        print("\n💡 This means Flask-Caching is NOT installed or server not running!")
        return False


def check_server():
    """Check if server is running"""
    print("\n" + "="*60)
    print("Server Status Check")
    print("="*60)
    
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code == 200:
            print(f"✅ Server is running at {BASE_URL}")
            return True
        else:
            print(f"❌ Server returned: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Cannot connect to server: {e}")
        print(f"\n💡 Make sure the server is running:")
        print(f"   cd mesh-scout && python3 web_server.py")
        return False


def check_flask_caching():
    """Check if Flask-Caching is installed"""
    print("\n" + "="*60)
    print("Flask-Caching Installation Check")
    print("="*60)
    
    try:
        import flask_caching
        print(f"✅ Flask-Caching is installed (version: {flask_caching.__version__})")
        return True
    except ImportError:
        print("❌ Flask-Caching is NOT installed!")
        print("\n💡 Install it with:")
        print("   pip3 install --user Flask-Caching")
        print("   # or")
        print("   pip3 install --break-system-packages Flask-Caching")
        return False


def main():
    """Main test function"""
    print("\n" + "="*60)
    print("🚀 Mesh-Scout Performance Testing Script")
    print("="*60)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Step 1: Check Flask-Caching installation
    flask_caching_installed = check_flask_caching()
    
    # Step 2: Check if server is running
    server_running = check_server()
    
    if not server_running:
        print("\n❌ Cannot proceed - server is not running!")
        sys.exit(1)
    
    # Step 3: Check cache status
    cache_working = check_cache_status()
    
    if not cache_working:
        print("\n⚠️  Cache is not working properly!")
        if not flask_caching_installed:
            print("\n💡 Next steps:")
            print("   1. Install Flask-Caching: pip3 install --user Flask-Caching")
            print("   2. Restart the server: python3 web_server.py")
            print("   3. Run this test again: python3 test_performance.py")
        sys.exit(1)
    
    # Step 4: Run performance tests
    print("\n" + "="*60)
    print("🧪 Running Performance Tests")
    print("="*60)
    print("\nTesting each endpoint 3 times to measure cache effectiveness...")
    
    all_results = {}
    for endpoint, name in ENDPOINTS:
        url = BASE_URL + endpoint
        results = test_endpoint(url, name)
        if results:
            all_results[name] = results
    
    # Summary
    if all_results:
        print("\n" + "="*60)
        print("📈 Performance Summary")
        print("="*60)
        
        for name, times in all_results.items():
            if len(times) > 1:
                first = times[0]
                avg_cached = sum(times[1:]) / (len(times) - 1)
                speedup = first / avg_cached if avg_cached > 0 else 0
                
                status = "✅" if speedup > 2 else "⚠️"
                print(f"\n{status} {name}:")
                print(f"    Cold: {first:.3f}s → Cached: {avg_cached:.3f}s ({speedup:.1f}x faster)")
        
        # Overall assessment
        print("\n" + "="*60)
        print("🎯 Overall Assessment")
        print("="*60)
        
        speedups = []
        for times in all_results.values():
            if len(times) > 1:
                first = times[0]
                avg_cached = sum(times[1:]) / (len(times) - 1)
                speedups.append(first / avg_cached if avg_cached > 0 else 0)
        
        if speedups:
            avg_speedup = sum(speedups) / len(speedups)
            print(f"\nAverage speedup: {avg_speedup:.1f}x")
            
            if avg_speedup > 5:
                print("✅ EXCELLENT: Cache is working very well!")
            elif avg_speedup > 2:
                print("✅ GOOD: Cache is working as expected")
            else:
                print("⚠️  WARNING: Cache speedup is lower than expected")
                print("    This might indicate that cache is not properly configured")
    
    print("\n" + "="*60)
    print("Test completed!")
    print("="*60 + "\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(0)
