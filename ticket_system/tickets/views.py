from django.http import Http404

from rest_framework import status, viewsets
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend

from .models import StatusChoices, Ticket
from .serializers import TicketSerializer


class TicketViewSet(viewsets.ModelViewSet):
    queryset = Ticket.objects.all()
    serializer_class = TicketSerializer
    permission_classes = [AllowAny]  # fully open for POC

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]

    # simple exact filters + useful lookups:
    #   ?id=1 | ?id__in=1,2,3
    #   ?title__icontains=outage
    #   ?created_at__gte=2025-09-20T00:00:00Z
    #   ?resolution_status=open  |  ?resolution_status__in=open,closed
    filterset_fields = {
        "id": ["exact", "in"],
        "title": ["icontains"],
        "created": ["gte", "lte"],
        "resolution_status": [
            "exact",
            "in",
        ],
    }

    search_fields = ["title", "description"]  # fuzzy search across text
    #  e.g. GET /api/tickets/?search=email
    ordering_fields = ["created", "updated", "title"]

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

    class InvalidFieldsError(ValidationError):
        status_code = status.HTTP_400_BAD_REQUEST
        default_code = "invalid_fields"

        def __init__(self, fields: set[str]):
            detail = {
                field: ["Unknown field sent in request body."] for field in fields
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

    def _validate_fields(self, request):
        allowed_fields = set(self.serializer_class.Meta.fields)
        provided_fields = set(request.data.keys())
        invalid_fields = provided_fields - allowed_fields
        if invalid_fields:
            raise self.InvalidFieldsError(invalid_fields)

    def _validate_status(self, request):
        if "resolution_status" in request.data:
            status_value = request.data["resolution_status"]
            if status_value not in StatusChoices.values:
                raise self.InvalidStatusError(status_value)

    def update(self, request, *args, **kwargs):
        self._validate_fields(request)
        self._validate_status(request)
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        self._validate_fields(request)
        self._validate_status(request)
        return super().partial_update(request, *args, **kwargs)
