from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json

@csrf_exempt
def predict(request, model_id):

    if request.method == "POST":
        try:
            body = json.loads(request.body)

            return JsonResponse({
                "message": "POST working",
                "model_id": model_id,
                "input": body
            })
        except:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

    return JsonResponse({
        "message": "GET working",
        "model_id": model_id
    })