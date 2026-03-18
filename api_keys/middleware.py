class APIKeyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        api_key = request.headers.get("Authorization")

        # later: validate key
        request.api_key = api_key

        return self.get_response(request)