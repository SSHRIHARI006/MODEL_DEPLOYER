from django.http import JsonResponse

def success_response(data, status=200):
    return JsonResponse({
        "success": True,
        "data": data
    }, status=status)


def error_response(message, code="ERROR", status=400):
    return JsonResponse({
        "success": False,
        "error": code,
        "message": message
    }, status=status)