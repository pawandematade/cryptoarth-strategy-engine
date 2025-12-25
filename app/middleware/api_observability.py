"""
API Observability Middleware
Tracks request count, latency, and error rates per endpoint
Read-only metrics collection - no request mutation
"""
import time
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from collections import defaultdict
from datetime import datetime
import json

logger = logging.getLogger(__name__)

# In-memory metrics storage (can be replaced with Redis/Prometheus in production)
_metrics = {
    "request_count": defaultdict(int),
    "request_latency": defaultdict(list),
    "error_count": defaultdict(lambda: defaultdict(int)),
    "last_updated": datetime.utcnow().isoformat()
}


class APIObservabilityMiddleware(BaseHTTPMiddleware):
    """
    Middleware to track API metrics
    Read-only - does NOT modify requests or responses
    """
    
    async def dispatch(self, request: Request, call_next):
        # Start timing
        start_time = time.time()
        
        # Extract endpoint path
        endpoint = request.url.path
        
        # Track request count
        _metrics["request_count"][endpoint] += 1
        
        # Process request
        try:
            response = await call_next(request)
            
            # Calculate latency
            latency_ms = (time.time() - start_time) * 1000
            
            # Track latency (keep last 1000 requests per endpoint)
            if endpoint not in _metrics["request_latency"]:
                _metrics["request_latency"][endpoint] = []
            _metrics["request_latency"][endpoint].append(latency_ms)
            if len(_metrics["request_latency"][endpoint]) > 1000:
                _metrics["request_latency"][endpoint].pop(0)
            
            # Track error rates
            status_code = response.status_code
            if status_code >= 400:
                _metrics["error_count"][endpoint][status_code] += 1
                logger.warning(
                    f"API Error: {request.method} {endpoint} -> {status_code} "
                    f"(latency: {latency_ms:.2f}ms)"
                )
            else:
                # Log slow requests (> 1 second)
                if latency_ms > 1000:
                    logger.warning(
                        f"Slow API: {request.method} {endpoint} -> {status_code} "
                        f"(latency: {latency_ms:.2f}ms)"
                    )
            
            # Update last updated timestamp
            _metrics["last_updated"] = datetime.utcnow().isoformat()
            
            return response
            
        except Exception as e:
            # Track exception as 500 error
            _metrics["error_count"][endpoint][500] += 1
            logger.error(f"API Exception: {request.method} {endpoint} -> {e}")
            raise


def get_api_metrics() -> dict:
    """
    Get current API metrics
    Returns aggregated statistics
    """
    metrics_summary = {
        "timestamp": datetime.utcnow().isoformat(),
        "endpoints": {}
    }
    
    for endpoint, count in _metrics["request_count"].items():
        latencies = _metrics["request_latency"].get(endpoint, [])
        errors = _metrics["error_count"].get(endpoint, {})
        
        # Calculate percentiles
        if latencies:
            sorted_latencies = sorted(latencies)
            p50 = sorted_latencies[int(len(sorted_latencies) * 0.5)]
            p95 = sorted_latencies[int(len(sorted_latencies) * 0.95)] if len(sorted_latencies) > 20 else sorted_latencies[-1]
            p99 = sorted_latencies[int(len(sorted_latencies) * 0.99)] if len(sorted_latencies) > 100 else sorted_latencies[-1]
        else:
            p50 = p95 = p99 = 0
        
        # Calculate error rates
        total_errors = sum(errors.values())
        error_rate = (total_errors / count * 100) if count > 0 else 0
        
        metrics_summary["endpoints"][endpoint] = {
            "request_count": count,
            "latency_ms": {
                "p50": round(p50, 2),
                "p95": round(p95, 2),
                "p99": round(p99, 2),
                "avg": round(sum(latencies) / len(latencies), 2) if latencies else 0
            },
            "error_count": total_errors,
            "error_rate_percent": round(error_rate, 2),
            "errors_by_status": dict(errors)
        }
    
    return metrics_summary


def get_critical_api_metrics() -> dict:
    """
    Get metrics for critical performance APIs only
    Filters to performance-related endpoints
    """
    all_metrics = get_api_metrics()
    critical_endpoints = [
        "/auth/strategy",
        "/auth/strategy/{id}/performance",
        "/auth/strategy/{id}/performance/summary",
        "/auth/strategy/{id}/performance/daily",
        "/auth/strategy/{id}/performance/trades"
    ]
    
    critical_metrics = {
        "timestamp": all_metrics["timestamp"],
        "endpoints": {}
    }
    
    for endpoint_pattern in critical_endpoints:
        # Match endpoints that start with pattern
        for endpoint, metrics in all_metrics["endpoints"].items():
            if endpoint.startswith(endpoint_pattern.replace("{id}", "")):
                critical_metrics["endpoints"][endpoint] = metrics
    
    return critical_metrics

