#!/usr/bin/env python
"""Generate an authoritative API inventory from Django URLs and FastAPI routes.

Outputs:
  - test-results/inventory.json
  - Formatted console table
"""
from __future__ import annotations

import inspect
import json
import os
import sys
from pathlib import Path

# Setup Django environment
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_test")

import django
django.setup()

from django.urls import URLPattern, URLResolver, get_resolver
from rest_framework.views import APIView


def get_django_routes(resolver, prefix=""):
    routes = []
    for pattern in resolver.url_patterns:
        if isinstance(pattern, URLResolver):
            routes.extend(get_django_routes(pattern, prefix + str(pattern.pattern)))
        elif isinstance(pattern, URLPattern):
            raw_path = "/" + (prefix + str(pattern.pattern)).lstrip("^").rstrip("$")
            # Normalise path formatting
            clean_path = raw_path.replace("\\", "")
            callback = pattern.callback
            view_class = getattr(callback, "view_class", None)

            methods = []
            auth_required = False
            permissions = []
            throttles = []

            if view_class and issubclass(view_class, APIView):
                for m in ["GET", "POST", "PUT", "PATCH", "DELETE"]:
                    if hasattr(view_class, m.lower()):
                        methods.append(m)

                perm_classes = getattr(view_class, "permission_classes", [])
                permissions = [p.__name__ for p in perm_classes]
                auth_required = any(p != "AllowAny" for p in permissions)

                throttle_classes = getattr(view_class, "throttle_classes", [])
                throttles = [t.__name__ for t in throttle_classes]
                scope = getattr(view_class, "throttle_scope", None)
                if scope:
                    throttles.append(f"scope:{scope}")
            else:
                methods = ["GET", "POST"]

            handler_name = (
                f"{view_class.__module__}.{view_class.__name__}"
                if view_class
                else getattr(callback, "__name__", str(callback))
            )

            routes.append({
                "service": "django",
                "path": clean_path,
                "name": pattern.name or "",
                "methods": sorted(methods),
                "auth_required": auth_required,
                "permissions": permissions,
                "throttles": throttles,
                "handler": handler_name,
            })
    return routes


def get_fastapi_routes():
    try:
        from runners.worker import app as fastapi_app
    except Exception as e:
        return []

    routes = []
    for route in getattr(fastapi_app, "routes", []):
        path = getattr(route, "path", "")
        if not path or path in ("/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"):
            continue

        methods = sorted(list(getattr(route, "methods", set()) - {"HEAD", "OPTIONS"}))
        name = getattr(route, "name", "")
        endpoint = getattr(route, "endpoint", None)
        handler_name = f"{endpoint.__module__}.{endpoint.__name__}" if endpoint else name

        # Check if auth dependency is attached
        dependencies = getattr(route, "dependencies", [])
        auth_required = any("require_runner_auth" in str(d) for d in dependencies)

        routes.append({
            "service": "fastapi_runner",
            "path": path,
            "name": name,
            "methods": methods,
            "auth_required": auth_required,
            "permissions": ["require_runner_auth"] if auth_required else ["public"],
            "throttles": [],
            "handler": handler_name,
        })
    return routes


def main():
    resolver = get_resolver()
    django_routes = get_django_routes(resolver)
    fastapi_routes = get_fastapi_routes()
    all_routes = django_routes + fastapi_routes

    # Filter out Django admin builtins for clean project API view
    project_routes = [r for r in all_routes if not r["path"].startswith("/admin/")]

    out_dir = repo_root / "test-results"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "inventory.json"

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(project_routes, f, indent=2)

    print(f"API Inventory generated: {len(project_routes)} project endpoints (saved to {out_file})\n")
    print(f"{'Service':<14} {'Methods':<18} {'Auth':<6} {'Path':<45} {'Permissions'}")
    print("-" * 105)
    for r in project_routes:
        methods_str = ",".join(r["methods"])
        auth_str = "YES" if r["auth_required"] else "NO"
        perms_str = ",".join(r["permissions"]) if r["permissions"] else "-"
        print(f"{r['service']:<14} {methods_str:<18} {auth_str:<6} {r['path']:<45} {perms_str}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
