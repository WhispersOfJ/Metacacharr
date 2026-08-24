from rest_framework import serializers


class ConfirmRequestSerializer(serializers.Serializer):
    """Request body schema shared by all three host-action endpoints.
    confirm defaults to False - matching the FastAPI-era
    HostActionRequest(BaseModel) - so an omitted field is treated as an
    explicit no."""

    confirm = serializers.BooleanField(default=False)
