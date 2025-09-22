from django.http import Http404

from rest_framework import status, viewsets
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny

from .models import StatusChoices, Ticket
from .serializers import TicketSerializer


class TicketViewSet(viewsets.ModelViewSet):
    queryset = Ticket.objects.all()
    serializer_class = TicketSerializer
    permission_classes = [AllowAny]  # fully open for POC

    class InvalidStatusError(ValidationError):
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        default_code = "invalid_status"

        def __init__(self, status_value: str):
            allowed = ", ".join(StatusChoices.values)
            detail = {
                "resolution_status": [
                    f"Invalid status '{status_value}'. Allowed values are: {allowed}."
                ]
            }
            super().__init__(detail=detail)

    def get_object(self):
        try:
            return super().get_object()
        except Http404 as exc:
            lookup_value = self.kwargs.get(self.lookup_field)
            raise NotFound(
                detail=f"Ticket with id '{lookup_value}' was not found."
            ) from exc

    def _validate_status(self, request):
        if "resolution_status" in request.data:
            status_value = request.data["resolution_status"]
            if status_value not in StatusChoices.values:
                raise self.InvalidStatusError(status_value)

    def update(self, request, *args, **kwargs):
        self._validate_status(request)
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        self._validate_status(request)
        return super().partial_update(request, *args, **kwargs)
