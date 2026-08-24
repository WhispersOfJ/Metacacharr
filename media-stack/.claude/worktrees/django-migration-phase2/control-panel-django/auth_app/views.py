from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from core.models import User


def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username", "")
        password = request.POST.get("password", "")
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            return render(request, "auth_app/login.html", {"error": "Invalid username or password"})

        if not user.check_password(password):
            return render(request, "auth_app/login.html", {"error": "Invalid username or password"})

        request.session.cycle_key()
        request.session["user_id"] = user.id
        return redirect("/")

    return render(request, "auth_app/login.html")


@require_POST
def logout_view(request):
    request.session.pop("user_id", None)
    return redirect("auth_app:login")
