from django.shortcuts import render


def home(request):
    return render(request, "webapp/home.html")


def auth_page(request):
    return render(request, "webapp/auth.html")


def dashboard_page(request):
    return render(request, "webapp/dashboard.html")


def model_detail_page(request, model_id):
    return render(request, "webapp/model_detail.html", {"model_id": model_id})