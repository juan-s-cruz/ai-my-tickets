"""Middleware for simulating unstable network conditions on API endpoints."""

import random
import time

from django.http import HttpResponse


class SimulatedNetworkConditionsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info or ""

        if path == "/api" or path.startswith("/api/"):
            time.sleep(random.uniform(0.25, 2.0))

            if random.random() < 0.25:
                return HttpResponse(
                    "ERROR 503: Simulated service disruption. Please retry.",
                    status=503,
                )

        return self.get_response(request)
