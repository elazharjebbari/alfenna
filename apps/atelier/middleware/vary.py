from ..config.registry import get_vary_fields

class VaryHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        vary = set((response.get("Vary") or "").split(",")) if response.get("Vary") else set()
        for f in get_vary_fields():
            if f:
                vary.add(f)
        if vary:
            response["Vary"] = ", ".join(sorted([v for v in vary if v]))
        return response