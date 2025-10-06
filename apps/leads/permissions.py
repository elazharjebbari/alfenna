from rest_framework.permissions import BasePermission

class PublicPOSTOnly(BasePermission):
    def has_permission(self, request, view):
        return request.method == "POST"